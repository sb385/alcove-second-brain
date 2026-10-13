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


def _when(iso: str | None, now: datetime) -> str:
    if not iso:
        return "never"
    t = datetime.fromisoformat(iso).astimezone(settings.tz)
    if t.date() == now.date():
        return f"Today {t:%H:%M}"
    if t.date() == (now - timedelta(days=1)).date():
        return f"Yesterday {t:%H:%M}"
    return f"{t:%d %b %H:%M}"


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
.sync{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px;margin:18px 0 0}
.sync-head{display:flex;justify-content:space-between;align-items:baseline;gap:8px;flex-wrap:wrap;margin-bottom:12px}
.sync-head h2{margin:0}.sync-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(200px,100%),1fr));gap:10px}
.src{border:1px solid var(--line);border-radius:8px;padding:10px 12px;border-left:4px solid var(--line)}
.src.ok{border-left-color:var(--green)}.src.failed{border-left-color:var(--red)}
.src.stale{border-left-color:var(--amber)}.src.none{border-left-color:var(--mute)}
.src-top{display:flex;justify-content:space-between;align-items:center;gap:6px}
.src-name{font-weight:600}.badge{font-size:12px;padding:2px 8px;border-radius:999px;background:var(--chip);white-space:nowrap}
.src.ok .badge{color:var(--green)}.src.failed .badge{color:var(--red)}.src.stale .badge{color:var(--amber)}
.src .m{margin-top:4px}
"""

_ICON = {"ok": "✓", "failed": "!", "stale": "◷", "none": "–"}


def html_box(log: dict, now: datetime) -> str:
    cs = cards(log, now)
    healthy = sum(1 for c in cs if c["state"] == "ok")
    items = []
    for c in cs:
        lines = "".join(f'<div class="m">{escape(x)}</div>' for x in (c["when"], c["counts"], c["note"]) if x)
        items.append(
            f'<div class="src {c["state"]}"><div class="src-top"><span class="src-name">{escape(c["label"])}</span>'
            f'<span class="badge">{_ICON[c["state"]]} {escape(c["badge"])}</span></div>{lines}</div>'
        )
    return (f'<section class="sync"><div class="sync-head"><h2>Data sync</h2>'
            f'<span class="sub">{healthy} of {len(cs)} sources up to date</span></div>'
            f'<div class="sync-grid">{"".join(items)}</div></section>')


def markdown_box(log: dict, now: datetime) -> list[str]:
    emoji = {"ok": "✅", "failed": "⚠️", "stale": "🕒", "none": "➖"}
    lines = ["## Data sync"]
    for c in cards(log, now):
        detail = " · ".join(x for x in (c["when"], c["counts"], c["note"]) if x)
        lines.append(f"- {emoji[c['state']]} **{c['label']}**: {c['badge']}" + (f" ({detail})" if detail else ""))
    return lines
