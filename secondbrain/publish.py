"""Upload the latest dashboard, Excel and summary to the hosted web app (app.py).

    python -m secondbrain.publish

Needs PUBLISH_URL (e.g. https://second-brain.example.com) and UPLOAD_TOKEN in .env.
"""
from __future__ import annotations

import os
import sys

import requests

from .config import settings


def _rerender() -> None:
    import argparse

    from . import cloud
    from .config import ROOT
    meetings = ROOT / ".run" / "meetings.json"
    cloud.cmd_render(argparse.Namespace(meetings=str(meetings) if meetings.exists() else None))


def main() -> int:
    url = os.getenv("PUBLISH_URL", "").rstrip("/")
    token = os.getenv("UPLOAD_TOKEN", "")
    if not url or not token:
        print("[publish] PUBLISH_URL / UPLOAD_TOKEN not set; skipped")
        return 0
    out = settings.dashboard_html.parent
    paths = {
        "dashboard": settings.dashboard_html,
        "excel": settings.master_xlsx,
        "summary": out / "whatsapp_summary.txt",
    }
    headers = {"Authorization": f"Bearer {token}"}

    # A password changed on the website lives only on the server, and redeploys
    # wipe it. Keep a copy (hash only) here and hand it back if it's missing.
    backup = settings.data_dir / "web_auth_override.json"
    form = {}
    state = requests.get(f"{url}/api/auth-state", headers=headers, timeout=30)
    if state.ok and state.json():
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_text(state.text, encoding="utf-8")
    elif state.ok and backup.exists():
        form["auth_override"] = backup.read_text(encoding="utf-8")

    # Apply dashboard clicks (Close / Follow up / Move / Shift) to the Excel, then
    # re-render so the uploaded page and Excel both reflect them.
    from . import web_actions
    web_actions.sync()
    _rerender()

    files = {k: (p.name, p.open("rb")) for k, p in paths.items() if p.exists()}
    try:
        r = requests.post(f"{url}/api/upload", files=files, data=form, headers=headers, timeout=60)
    finally:
        for _, fh in files.values():
            fh.close()
    if r.ok:
        print(f"[publish] uploaded {r.json().get('saved')} to {url}")
        return 0
    print(f"[publish] failed {r.status_code}: {r.text[:300]}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
