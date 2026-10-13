"""Daily run: pull sources -> Claude extraction -> Excel merge -> dashboard -> WhatsApp.

    python -m secondbrain.main                 # normal daily run
    python -m secondbrain.main --hours 72      # look back further
    python -m secondbrain.main --dry-run       # extract and print; write nothing, send nothing
    python -m secondbrain.main --no-whatsapp   # everything except the WhatsApp message
    python -m secondbrain.main --auth          # just do the Google OAuth consent
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta

from . import dashboard, notify
from .config import settings
from .extract import extract
from .insights import top_items
from .models import Extraction
from .sources import SourceItem, gcalendar, gmail, google_auth, whatsapp, wispr
from .store import Store

# Each returns SourceItems for the window; a failing source is skipped.
SOURCES = {
    "gmail": gmail.fetch,
    "calendar": gcalendar.fetch,
    "wispr": wispr.fetch,
    "whatsapp": whatsapp.fetch,
}

STATE_KEEP_DAYS = 14


def load_state() -> dict:
    if settings.state_file.exists():
        return json.loads(settings.state_file.read_text(encoding="utf-8"))
    return {"processed": {}}


def save_state(state: dict, now: datetime) -> None:
    cutoff = (now - timedelta(days=STATE_KEEP_DAYS)).isoformat()
    state["processed"] = {k: v for k, v in state["processed"].items() if v >= cutoff}
    state["last_run"] = now.isoformat()
    settings.state_file.parent.mkdir(parents=True, exist_ok=True)
    settings.state_file.write_text(json.dumps(state, indent=1), encoding="utf-8")


def run(hours: int, dry_run: bool, whatsapp: bool) -> int:
    now = datetime.now(settings.tz)
    since = now - timedelta(hours=hours)
    state = load_state()

    items: list[SourceItem] = []
    for name, fetch in SOURCES.items():
        try:
            got = fetch(since)
            print(f"[{name}] {len(got)} items since {since:%Y-%m-%d %H:%M}")
            items += got
        except Exception as e:  # one broken source shouldn't kill the run
            print(f"[{name}] FAILED: {e}", file=sys.stderr)

    fresh = [i for i in items if i.key not in state["processed"]]
    print(f"[run] {len(fresh)} new items ({len(items) - len(fresh)} already processed)")
    by_ref = {i.key: i for i in items}

    store = Store()
    totals: dict[str, int] = {}

    def on_batch(ex: Extraction, batch: list[SourceItem]):
        if dry_run:
            print(ex.model_dump_json(indent=2))
            return None
        for k, v in store.merge(ex, by_ref, now).items():
            totals[k] = totals.get(k, 0) + v
        for i in batch:
            state["processed"][i.key] = now.isoformat()
        return store.open_ledger()

    if fresh:
        extract(fresh, store.open_ledger(), now, on_batch=on_batch)
    if dry_run:
        return 0

    store.refresh_rollups(now.date())
    xlsx = store.save()
    save_state(state, now)
    print(f"[excel] {xlsx}  changes: {totals or 'none'}")

    try:
        meetings = gcalendar.upcoming(now)
    except Exception as e:
        print(f"[calendar] upcoming meetings FAILED: {e}", file=sys.stderr)
        meetings = None

    html = dashboard.write(store, now, meetings)
    print(f"[dashboard] {html}")

    summary = notify.compose(top_items(store, now), now, meetings)
    print("\n" + summary + "\n")
    (settings.dashboard_html.parent / "whatsapp_summary.txt").write_text(summary, encoding="utf-8")
    if whatsapp:
        notify.send(summary)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Daily second brain")
    p.add_argument("--hours", type=int, default=settings.lookback_hours)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-whatsapp", action="store_true")
    p.add_argument("--auth", action="store_true", help="run Google OAuth consent and exit")
    a = p.parse_args()
    if a.auth:
        google_auth.get_credentials(interactive=True)
        print(f"Google token (Gmail + Calendar) saved to {settings.google_token_file}")
        return 0
    return run(a.hours, a.dry_run, not a.no_whatsapp)


if __name__ == "__main__":
    sys.exit(main())
