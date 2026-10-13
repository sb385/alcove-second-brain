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
import secrets
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


def _check_password(given: str) -> bool:
    if os.environ.get("DASHBOARD_PASSWORD"):
        return _same(given, os.environ["DASHBOARD_PASSWORD"])
    rec = _AUTH.get("password")
    if not rec or not given:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", given.encode(), bytes.fromhex(rec["salt"]), rec["iterations"])
    return secrets.compare_digest(digest.hex(), rec["hash"])


def _check_token(given: str) -> bool:
    if os.environ.get("UPLOAD_TOKEN"):
        return _same(given, os.environ["UPLOAD_TOKEN"])
    want = _AUTH.get("upload_token_sha256", "")
    return bool(want and given) and secrets.compare_digest(hashlib.sha256(given.encode()).hexdigest(), want)


def login_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not (os.environ.get("DASHBOARD_PASSWORD") or _AUTH.get("password")):
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
        return ("<h2>No dashboard yet</h2><p>It appears after the next 8:00 run on the PC "
                "uploads it.</p>")
    html = path.read_text(encoding="utf-8")
    links = ('<div style="max-width:1180px;margin:0 auto;padding:12px 16px 0;font:14px system-ui">'
             f'<a href="{PREFIX}/excel">Download Excel</a> · '
             f'<a href="{PREFIX}/summary">WhatsApp summary</a></div>')
    return html.replace("<main>", links + "<main>", 1)


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
    return {"saved": saved}


@app.get("/health")
def health():
    return {"ok": True}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
