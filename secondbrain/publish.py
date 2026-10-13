"""Upload the latest dashboard, Excel and summary to the hosted web app (app.py).

    python -m secondbrain.publish

Needs PUBLISH_URL (e.g. https://second-brain.example.com) and UPLOAD_TOKEN in .env.
"""
from __future__ import annotations

import os
import sys

import requests

from .config import settings


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
    files = {k: (p.name, p.open("rb")) for k, p in paths.items() if p.exists()}
    try:
        r = requests.post(f"{url}/api/upload", files=files,
                          headers={"Authorization": f"Bearer {token}"}, timeout=60)
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
