"""PC side of cloud mode: copy new Wispr Flow meetings/notes into the
brain-data branch so the cloud routine can read them.

    python -m secondbrain.wispr_upload [--days 3]

Run hourly by register_wispr_upload.ps1. Needs the worktree created by
`scripts/brain_data.sh pull` (the .ps1 does that).
"""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timedelta

from .config import settings
from .sources import wispr


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=3)
    a = ap.parse_args()

    out = settings.data_dir / "wispr"
    out.mkdir(parents=True, exist_ok=True)
    since = datetime.now(settings.tz) - timedelta(days=a.days)
    written = 0
    for item in wispr.fetch(since):
        name = hashlib.sha1(item.ref.encode()).hexdigest()[:16] + ".json"
        path = out / name
        data = {**asdict(item), "timestamp": item.timestamp.isoformat()}
        if path.exists() and json.loads(path.read_text(encoding="utf-8")) == data:
            continue
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        written += 1
    print(f"[wispr-upload] {written} new/changed items in {out}")


if __name__ == "__main__":
    main()
