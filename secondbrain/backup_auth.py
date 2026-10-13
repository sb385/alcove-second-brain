"""Save the website-set password hash before anything can wipe it.

Run by the git pre-push hook (scripts/pre-push): every push redeploys the
site, and a redeploy wipes a password changed on the website. publish.py
restores it from this backup on the next upload.

    python -m secondbrain.backup_auth
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
        return 0
    try:
        r = requests.get(f"{url}/api/auth-state", headers={"Authorization": f"Bearer {token}"}, timeout=20)
    except requests.RequestException as e:
        print(f"[backup-auth] could not reach the site ({e}); push continues")
        return 0
    if r.ok and r.json():
        path = settings.data_dir / "web_auth_override.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(r.text, encoding="utf-8")
        print("[backup-auth] website password backed up")
    # Dashboard clicks queued on the site would also be wiped: apply them now.
    from . import web_actions
    web_actions.sync()
    return 0


if __name__ == "__main__":
    sys.exit(main())
