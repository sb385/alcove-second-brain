"""Cloud-routine entry points. The routine's Claude reads Gmail, Calendar and
WhatsApp through connectors and does the extraction itself; these commands do
the deterministic parts (ledger, merge, dashboard, ranking).

    python -m secondbrain.cloud schema             # JSON schema of the run file Claude writes
    python -m secondbrain.cloud ledger             # open items + known people (for matching)
    python -m secondbrain.cloud wispr --hours 24   # Wispr items uploaded from the PC
    python -m secondbrain.cloud merge RUN.json     # validate + merge into the Excel
    python -m secondbrain.cloud render [--meetings MEETINGS.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ValidationError

from . import dashboard, notify
from .config import settings
from .insights import top_items
from .models import Extraction
from .sources import SourceItem
from .store import Store
from . import sync_status


class SourceRef(BaseModel):
    ref: str            # e.g. "gmail:<threadId>", "whatsapp:<contact>", "wispr:meeting:<id>:summary"
    source: str         # gmail | calendar | whatsapp | wispr
    title: str
    link: Optional[str] = None


class RunFile(BaseModel):
    sources: list[SourceRef]
    extraction: Extraction


class MeetingIn(BaseModel):
    title: str
    start: str          # ISO 8601 with offset
    end: str
    all_day: bool = False
    attendees: list[dict] = []   # {"name","email","response"}
    my_response: str = "accepted"
    location: str = ""
    join_link: str = ""
    link: str = ""


def _now() -> datetime:
    return datetime.now(settings.tz)


def cmd_schema(_a) -> None:
    print(json.dumps({"run_file": RunFile.model_json_schema(),
                      "meetings_file": {"type": "array", "items": MeetingIn.model_json_schema()}}, indent=1))


def cmd_ledger(_a) -> None:
    store = Store()
    led = store.open_ledger()
    led["people"] = [
        {k: p.get(k) for k in ("Name", "Email", "Phone", "Organisation", "Role") if p.get(k)}
        for p in store.rows["People"]
    ]
    print(json.dumps(led, ensure_ascii=False, indent=1, default=str))


def cmd_wispr(a) -> None:
    since = _now() - timedelta(hours=a.hours)
    folder = settings.data_dir / "wispr"
    shown = 0
    for p in sorted(folder.glob("*.json")) if folder.exists() else []:
        d = json.loads(p.read_text(encoding="utf-8"))
        ts = datetime.fromisoformat(d["timestamp"])
        if ts < since:
            continue
        item = SourceItem(**{**d, "timestamp": ts})
        print(item.render(), end="\n\n")
        shown += 1
    print(f"<!-- {shown} Wispr items since {since:%Y-%m-%d %H:%M} -->")


def cmd_merge(a) -> None:
    raw = Path(a.file).read_text(encoding="utf-8")
    try:
        run = RunFile.model_validate_json(raw)
    except ValidationError as e:
        print(f"INVALID run file, fix and retry:\n{e}", file=sys.stderr)
        sys.exit(2)
    now = _now()
    items = {
        s.ref: SourceItem(source=s.source, ref=s.ref, timestamp=now, title=s.title, author="", link=s.link or "")
        for s in run.sources
    }
    store = Store()
    stats = store.merge(run.extraction, items, now)
    store.refresh_rollups(now.date())
    path = store.save()
    archive = settings.data_dir / "runs" / f"{now:%Y-%m-%d}"
    archive.mkdir(parents=True, exist_ok=True)
    (archive / f"run-{now:%H%M}.json").write_text(raw, encoding="utf-8")
    print(f"merged into {path}: {stats}")


def _meetings(path: str | None):
    if not path:
        return None
    from .sources.gcalendar import Attendee, Meeting
    out = []
    for m in json.loads(Path(path).read_text(encoding="utf-8")):
        m = MeetingIn.model_validate(m)
        out.append(Meeting(
            id=m.link or m.title, title=m.title,
            start=datetime.fromisoformat(m.start).astimezone(settings.tz),
            end=datetime.fromisoformat(m.end).astimezone(settings.tz),
            all_day=m.all_day, organizer="",
            attendees=[Attendee(x.get("name") or x.get("email", ""), x.get("email", ""), x.get("response", ""))
                       for x in m.attendees],
            location=m.location, join_link=m.join_link, link=m.link, my_response=m.my_response,
        ))
    return sorted(out, key=lambda m: m.start)


def cmd_render(a) -> None:
    now = _now()
    store = Store()
    meetings = _meetings(a.meetings)
    sync = sync_status.merge_run()
    html = dashboard.write(store, now, meetings, sync)
    md_path = settings.dashboard_html.with_suffix(".md")
    md_path.write_text(dashboard.render_markdown(store, now, meetings, sync), encoding="utf-8")
    summary = notify.compose(top_items(store, now), now, meetings)
    (settings.dashboard_html.parent / "whatsapp_summary.txt").write_text(summary, encoding="utf-8")
    print(f"dashboard html: {html}\ndashboard markdown: {md_path}\n\n--- WhatsApp summary ---\n{summary}")


def cmd_sync_status(a) -> None:
    sync_status.record(a.source, a.status, a.read, a.used, a.note or "", _now())
    print(f"recorded {a.source}: {a.status}")


def main() -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("schema").set_defaults(fn=cmd_schema)
    sub.add_parser("ledger").set_defaults(fn=cmd_ledger)
    w = sub.add_parser("wispr")
    w.add_argument("--hours", type=int, default=settings.lookback_hours)
    w.set_defaults(fn=cmd_wispr)
    m = sub.add_parser("merge")
    m.add_argument("file")
    m.set_defaults(fn=cmd_merge)
    s = sub.add_parser("sync-status", help="record one source's result for the dashboard box")
    s.add_argument("--source", required=True, choices=list(sync_status.SOURCES))
    s.add_argument("--status", required=True, choices=["ok", "failed", "skipped"])
    s.add_argument("--read", type=int, help="items read from the source")
    s.add_argument("--used", type=int, help="items that had business content")
    s.add_argument("--note", help="one short line, e.g. the error or what was skipped")
    s.set_defaults(fn=cmd_sync_status)
    r = sub.add_parser("render")
    r.add_argument("--meetings")
    r.set_defaults(fn=cmd_render)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
