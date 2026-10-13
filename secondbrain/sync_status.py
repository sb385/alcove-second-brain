"""Per-source sync status shown at the top of the dashboard.

During a run, each source step records its result:
    python -m secondbrain.cloud sync-status --source gmail --status ok --read 42 --used 13
That lands in .run/sync_status.json. `cloud render` folds it into the
persistent log (DATA_DIR/sync_log.json), which keeps the last result and the
last successful sync per source, so a failed or skipped source still shows
when it last worked.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from html import escape
from pathlib import Path

from .config import ROOT, settings

SOURCES = {
    "gmail": "Gmail",
    "calendar": "Google Calendar",
    "whatsapp": "WhatsApp",
    "wispr": "Wispr Flow",
}
RUN_FILE = ROOT / ".run" / "sync_status.json"
STALE_AFTER = timedelta(hours=26)


def _log_path() -> Path:
    return settings.data_dir / "sync_log.json"


def record(source: str, status: str, read: int | None, used: int | None, note: str, now: datetime) -> None:
    RUN_FILE.parent.mkdir(parents=True, exist_ok=True)
    run = json.loads(RUN_FILE.read_text(encoding="utf-8")) if RUN_FILE.exists() else {}
    run[source] = {"status": status, "read": read, "used": used, "note": note, "at": now.isoformat()}
    RUN_FILE.write_text(json.dumps(run, indent=1), encoding="utf-8")


def merge_run() -> dict:
    """Fold this run's results into the persistent log and return the log."""
    path = _log_path()
    log = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if RUN_FILE.exists():
        for src, r in json.loads(RUN_FILE.read_text(encoding="utf-8")).items():
            entry = log.setdefault(src, {})
            entry.update({k: r.get(k) for k in ("status", "read", "used", "note")})
            entry["last_run"] = r["at"]
            if r["status"] == "ok":
                entry["last_ok"] = r["at"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(log, indent=1), encoding="utf-8")
        RUN_FILE.unlink()  # consumed; next run starts clean
    return log


def load() -> dict:
    path = _log_path()
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def clock(t: datetime) -> str:
    """12-hour time like 2:43 PM."""
    return t.strftime("%I:%M %p").lstrip("0")


def _when(iso: str | None, now: datetime) -> str:
    if not iso:
        return "never"
    t = datetime.fromisoformat(iso).astimezone(settings.tz)
    if t.date() == now.date():
        return f"Today {clock(t)}"
    if t.date() == (now - timedelta(days=1)).date():
        return f"Yesterday {clock(t)}"
    return f"{t:%d %b} {clock(t)}"


def cards(log: dict, now: datetime) -> list[dict]:
    """One view-model per source: label, state (ok/failed/stale/none), text lines."""
    out = []
    for key, label in SOURCES.items():
        e = log.get(key)
        if not e:
            out.append({"label": label, "state": "none", "badge": "Not synced yet",
                        "when": "", "counts": "", "note": ""})
            continue
        last_run = datetime.fromisoformat(e["last_run"]).astimezone(settings.tz)
        if e.get("status") != "ok":
            state, badge = "failed", "Failed" if e.get("status") == "failed" else "Skipped"
        elif now - last_run > STALE_AFTER:
            state, badge = "stale", "Out of date"
        else:
            state, badge = "ok", "Synced"
        bits = []
        if e.get("read") is not None:
            bits.append(f"{e['read']} read")
        if e.get("used") is not None:
            bits.append(f"{e['used']} used")
        when = f"Last sync {_when(e['last_run'], now)}"
        if state != "ok" and e.get("last_ok") != e.get("last_run"):
            when += f" · last good {_when(e.get('last_ok'), now)}"
        out.append({"label": label, "state": state, "badge": badge, "when": when,
                    "counts": " · ".join(bits), "note": e.get("note") or ""})
    return out


CSS = """
.sync{display:flex;flex-wrap:wrap;align-items:center;gap:6px 14px;background:var(--card);
border:1px solid var(--line);border-radius:10px;padding:10px 14px;margin:14px 0 0;font-size:14px}
.sync .src{white-space:nowrap;font-weight:600}.sync .src i{font-style:normal;margin-right:3px}
.sync .ok i{color:var(--green)}.sync .failed i{color:var(--red)}.sync .stale i{color:var(--amber)}.sync .none i{color:var(--mute)}
.sync .when{margin-left:auto;color:var(--mute);white-space:nowrap}
"""

_ICON = {"ok": "✓", "failed": "✗", "stale": "◷", "none": "–"}


def _last_sync(log: dict) -> str:
    runs = [e["last_run"] for e in log.values() if e.get("last_run")]
    if not runs:
        return "Not synced yet"
    t = datetime.fromisoformat(max(runs)).astimezone(settings.tz)
    return f"Last sync {t:%d %b %Y}, {clock(t)}"


def html_box(log: dict, now: datetime) -> str:
    """One compact line: a tick per source, then the last sync date and time.
    Hover a source for details (counts, or why it failed)."""
    items = []
    for c in cards(log, now):
        tip = " · ".join(x for x in (c["badge"], c["when"], c["counts"], c["note"]) if x)
        items.append(f'<span class="src {c["state"]}" title="{escape(tip)}">'
                     f'<i>{_ICON[c["state"]]}</i>{escape(c["label"])}</span>')
    return f'<div class="sync">{"".join(items)}<span class="when">{_last_sync(log)}</span></div>'


def markdown_box(log: dict, now: datetime) -> list[str]:
    emoji = {"ok": "✅", "failed": "⚠️", "stale": "🕒", "none": "➖"}
    line = " · ".join(f"{emoji[c['state']]} {c['label']}" for c in cards(log, now))
    return [f"{line} — {_last_sync(log)}"]
