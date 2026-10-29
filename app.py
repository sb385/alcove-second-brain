"""Web app for the hosted dashboard.

The 8am job runs on the PC (it needs Wispr Flow and the Claude connectors) and
then uploads its outputs here with secondbrain/publish.py. This app only stores
and serves the latest upload, behind a password.

Environment variables (set them on the hosting platform):
    DASHBOARD_PASSWORD  password for the website (username: anything)
    UPLOAD_TOKEN        shared secret the PC uses to upload; long and random
    STORE_DIR           where uploads are kept (default ./published); use a
                        persistent volume if the platform offers one
    PORT                set by the platform
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

from flask import Flask, Response, abort, request, send_file

# The platform mounts the app under a sub-path (e.g. /p/second-brain) and sets
# SCRIPT_NAME, but its proxy strips that prefix before forwarding. gunicorn
# then rejects every request ("does not start with SCRIPT_NAME"). Take the
# prefix out of the environment and use it only for building links.
PREFIX = os.environ.pop("SCRIPT_NAME", "").rstrip("/")

app = Flask(__name__)


class _Prefix:
    """Accept paths with or without the mount prefix."""

    def __init__(self, wsgi):
        self.wsgi = wsgi

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO", "")
        if PREFIX and path.startswith(PREFIX):
            environ["PATH_INFO"] = path[len(PREFIX):] or "/"
        environ["SCRIPT_NAME"] = PREFIX
        return self.wsgi(environ, start_response)


app.wsgi_app = _Prefix(app.wsgi_app)
STORE = Path(os.environ.get("STORE_DIR", "published"))
STORE.mkdir(parents=True, exist_ok=True)
FILES = {
    "dashboard": "dashboard.html",
    "excel": "second_brain.xlsx",
    "summary": "whatsapp_summary.txt",
}
MAX_UPLOAD = 20 * 1024 * 1024
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD


def _same(a: str, b: str) -> bool:
    return bool(a) and bool(b) and secrets.compare_digest(a.encode(), b.encode())


# The hosting platform has no environment variables, so web_auth.json (in the
# repo) holds only salted hashes. The real password and token live in the PC's
# .env. Create/rotate it with: python -m secondbrain.web_auth
_AUTH_FILE = Path(__file__).with_name("web_auth.json")
_AUTH = json.loads(_AUTH_FILE.read_text(encoding="utf-8")) if _AUTH_FILE.exists() else {}


# A password changed on the website is stored here (hash only). Redeploys wipe
# STORE, so the PC's publish step backs it up and restores it on upload.
OVERRIDE = STORE / "auth_override.json"
PBKDF2_ITERATIONS = 310_000


def _password_record() -> dict | None:
    return _AUTH.get("password")


def _override_record() -> dict | None:
    if OVERRIDE.exists():
        try:
            return json.loads(OVERRIDE.read_text(encoding="utf-8"))["password"]
        except (ValueError, KeyError):
            pass
    return None


def _hash_password(password: str) -> dict:
    salt = secrets.token_bytes(16)
    return {"salt": salt.hex(), "iterations": PBKDF2_ITERATIONS,
            "hash": hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS).hex()}


def _matches(given: str, rec: dict | None) -> bool:
    if not rec or not given:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", given.encode(), bytes.fromhex(rec["salt"]), rec["iterations"])
    return secrets.compare_digest(digest.hex(), rec["hash"])


def _check_password(given: str) -> bool:
    # Two passwords open the site: the one set on the website (the everyday
    # password) and the PC's recovery password from web_auth.json, so a reset
    # from the PC works even when the website one is forgotten.
    if os.environ.get("DASHBOARD_PASSWORD"):
        return _same(given, os.environ["DASHBOARD_PASSWORD"])
    return _matches(given, _override_record()) or _matches(given, _password_record())


def _check_token(given: str) -> bool:
    if os.environ.get("UPLOAD_TOKEN"):
        return _same(given, os.environ["UPLOAD_TOKEN"])
    want = _AUTH.get("upload_token_sha256", "")
    return bool(want and given) and secrets.compare_digest(hashlib.sha256(given.encode()).hexdigest(), want)


def login_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not (os.environ.get("DASHBOARD_PASSWORD") or _password_record()):
            return fn(*a, **kw)  # no password configured: open (owner's choice for now)
        auth = request.authorization
        if not auth or not _check_password(auth.password or ""):
            return Response("Login required", 401, {"WWW-Authenticate": 'Basic realm="Second Brain"'})
        return fn(*a, **kw)
    return wrapper


@app.after_request
def no_cache_no_index(resp):
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["X-Robots-Tag"] = "noindex, nofollow"
    return resp


@app.get("/")
@login_required
def dashboard():
    path = STORE / FILES["dashboard"]
    if not path.exists():
        return ('<meta http-equiv="refresh" content="60"><div style="font:16px system-ui;max-width:520px;'
                'margin:80px auto;padding:0 16px;text-align:center"><h2>Refreshing the dashboard…</h2>'
                '<p>The site was just updated. Your dashboard will be back within a few minutes; '
                'this page reloads by itself.</p></div>')
    html = path.read_text(encoding="utf-8")
    links = ('<div style="max-width:1180px;margin:0 auto;padding:12px 16px 0;font:14px system-ui">'
             f'<a href="{PREFIX}/excel">Download Excel</a> · '
             f'<a href="{PREFIX}/summary">WhatsApp summary</a> · '
             f'<a href="{PREFIX}/change-password">Change password</a></div>')
    # Clicks made since the last sync, so the page shows them until the PC applies them.
    boot = json.dumps({"base": PREFIX, "pending": _read_actions()}).replace("</", "<\\/")
    html = html.replace("<body>", f"<body><script>window.SB={boot};</script>", 1)
    return html.replace("<main>", links + "<main>", 1)


# ---------- item actions (Close / Follow up / Move / Shift) ----------
# Clicks are queued here; the PC pulls them on every sync/publish, applies them
# to the Excel, then acknowledges them. Redeploys wipe STORE, so the PC also
# pulls them before every push (scripts/pre-push).
ACTIONS = STORE / "actions.jsonl"
ACTION_KINDS = {"done", "followup", "move", "shift", "nudge", "contact", "wmslink", "wmsunlink"}
# nudge   = "forwarded via WhatsApp/email to X" (logged in the item's Notes)
# contact = "Name|phone|email" added from the dashboard (item is empty)
# wmslink / wmsunlink = a Google Drive/Docs link added to or removed from the
#           Work Management tab (item is empty)
ITEM_RE = re.compile(r"^[CART]-\d{1,6}$")
LINK_RE = re.compile(r"^https://(docs|drive|sheets)\.google\.com/\S{5,490}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
try:
    from secondbrain.profiles import NAMES as PROFILE_NAMES
except Exception:  # keep the web app running even if the package moves
    PROFILE_NAMES = ()


def _read_actions() -> list[dict]:
    if not ACTIONS.exists():
        return []
    out = []
    for line in ACTIONS.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


@app.post("/api/item-action")
@login_required
def item_action():
    # A custom header can't be sent cross-site without CORS, which this app never
    # allows, so other websites can't trigger actions through a saved login.
    if request.headers.get("X-Second-Brain") != "1":
        abort(403)
    d = request.get_json(silent=True) or {}
    item, kind, value = str(d.get("item", "")), str(d.get("action", "")), str(d.get("value", ""))
    if kind not in ACTION_KINDS:
        abort(400)
    if kind == "contact":
        parts = value.split("|")
        if item or len(parts) != 3 or not parts[0].strip() or len(value) > 200 \
                or not (re.fullmatch(r"\d{10,15}", parts[1]) or "@" in parts[2]):
            abort(400)
    elif kind in ("wmslink", "wmsunlink"):
        if item or not LINK_RE.match(value):
            abort(400)
    elif not ITEM_RE.match(item):
        abort(400)
    if kind == "nudge" and not (0 < len(value) <= 160):
        abort(400)
    if kind in ("followup", "shift") and not DATE_RE.match(value):
        abort(400)
    if kind == "move" and value not in PROFILE_NAMES:
        abort(400)
    if kind == "shift" and item.startswith("R"):
        abort(400)  # risks have no due date
    rec = {"uid": secrets.token_hex(8), "item": item, "action": kind,
           "value": value if kind != "done" else "",
           "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    with ACTIONS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
    return rec


@app.get("/api/status")
def status():
    """For the PC's 10-minute check: is there a dashboard to show? (token required)"""
    sent = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not _check_token(sent):
        abort(401)
    return {"dashboard": (STORE / FILES["dashboard"]).exists()}


@app.get("/api/actions")
def actions_list():
    sent = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not _check_token(sent):
        abort(401)
    return {"actions": _read_actions()}


@app.post("/api/actions/ack")
def actions_ack():
    sent = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not _check_token(sent):
        abort(401)
    done = set((request.get_json(silent=True) or {}).get("uids", []))
    keep = [a for a in _read_actions() if a["uid"] not in done]
    tmp = ACTIONS.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(a) + "\n" for a in keep), encoding="utf-8")
    tmp.replace(ACTIONS)
    return {"remaining": len(keep)}


@app.get("/excel")
@login_required
def excel():
    path = STORE / FILES["excel"]
    if not path.exists():
        abort(404)
    return send_file(path, as_attachment=True, download_name="second_brain.xlsx")


@app.get("/summary")
@login_required
def summary():
    path = STORE / FILES["summary"]
    if not path.exists():
        abort(404)
    return Response(path.read_text(encoding="utf-8"), mimetype="text/plain; charset=utf-8")


@app.post("/api/upload")
def upload():
    sent = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not _check_token(sent):
        abort(401)
    saved = []
    for field, name in FILES.items():
        f = request.files.get(field)
        if f:
            tmp = STORE / (name + ".tmp")
            f.save(tmp)
            tmp.replace(STORE / name)
            saved.append(name)
    # Restore a website-set password after a redeploy wiped it (never overwrite one).
    backup = request.form.get("auth_override")
    if backup and not OVERRIDE.exists():
        rec = json.loads(backup)["password"]
        if {"salt", "iterations", "hash"} <= set(rec):
            OVERRIDE.write_text(json.dumps({"password": rec}), encoding="utf-8")
            saved.append("password (restored)")
    return {"saved": saved}


_FORM = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Change password</title>
<style>body{{margin:0;background:#f6f5f2;color:#1d2430;font:15px/1.45 system-ui,sans-serif}}
@media(prefers-color-scheme:dark){{body{{background:#121417;color:#e8eaed}}input{{background:#1b1e23;color:#e8eaed;border-color:#2b2f36}}}}
main{{max-width:420px;margin:40px auto;padding:0 16px}}label{{display:block;margin:14px 0 4px;font-weight:600}}
input{{width:100%;box-sizing:border-box;padding:10px;border:1px solid #ccc;border-radius:8px;font:inherit}}
button{{margin-top:18px;padding:10px 16px;border:0;border-radius:8px;background:#1f3a5f;color:#fff;font:inherit;cursor:pointer}}
.msg{{padding:10px;border-radius:8px;margin-top:14px}}.err{{background:#fde8e7;color:#b42318}}.ok{{background:#e7f6ec;color:#067647}}
a{{color:#1f6fd1}}</style></head><body><main>
<p><a href="{prefix}/">← Dashboard</a></p><h2>Change password</h2>{msg}
<form method="post" autocomplete="off">
<label for="c">Current password</label><input id="c" name="current" type="password" required>
<label for="n">New password (at least 8 characters)</label><input id="n" name="new" type="password" minlength="8" required>
<label for="r">Repeat new password</label><input id="r" name="repeat" type="password" minlength="8" required>
<button type="submit">Change password</button></form></main></body></html>"""


def _form(msg: str = "", ok: bool = False) -> str:
    box = f'<div class="msg {"ok" if ok else "err"}">{msg}</div>' if msg else ""
    return _FORM.format(prefix=PREFIX, msg=box)


@app.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if os.environ.get("DASHBOARD_PASSWORD"):
        return _form("The password is set on the server and can't be changed here.")
    if request.method == "GET":
        return _form()
    current = request.form.get("current", "")
    new = request.form.get("new", "")
    # Asking for the current password again also stops other sites from
    # changing it through the browser's saved login.
    if not _check_password(current):
        return _form("Current password is wrong."), 400
    if len(new) < 8:
        return _form("New password must be at least 8 characters."), 400
    if new != request.form.get("repeat", ""):
        return _form("The two new passwords don't match."), 400
    tmp = OVERRIDE.with_suffix(".tmp")
    tmp.write_text(json.dumps({"password": _hash_password(new)}), encoding="utf-8")
    tmp.replace(OVERRIDE)
    return _form("Password changed. Your browser will ask you to log in again with the "
                 "new password.", ok=True)


@app.get("/api/auth-state")
def auth_state():
    """For the PC's backup: the website-set password hash, if any (token required)."""
    sent = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not _check_token(sent):
        abort(401)
    return json.loads(OVERRIDE.read_text(encoding="utf-8")) if OVERRIDE.exists() else {}


@app.get("/health")
def health():
    return {"ok": True}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
