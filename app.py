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

import os
import secrets
from functools import wraps
from pathlib import Path

from flask import Flask, Response, abort, request, send_file

app = Flask(__name__)
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


def login_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        password = os.environ.get("DASHBOARD_PASSWORD", "")
        if not password:
            return Response("Set DASHBOARD_PASSWORD on the server first.", 503)
        auth = request.authorization
        if not auth or not _same(auth.password or "", password):
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
             '<a href="/excel">Download Excel</a> · <a href="/summary">WhatsApp summary</a></div>')
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
    token = os.environ.get("UPLOAD_TOKEN", "")
    sent = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not _same(sent, token):
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
