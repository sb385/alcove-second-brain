"""Wispr Flow connector: reads the app's local database (read-only).

Wispr Flow has no public API, but keeps everything on this PC:
- Meetings it recorded (summary, notes, to-dos, full transcript)  -> on by default
- Notes you wrote in Flow                                          -> on by default
- Dictations (everything you spoke into any app)                   -> opt-in, see .env

Nothing is written to Wispr's files; the DB is opened with mode=ro.
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from ..config import settings
from .base import SourceItem

MAX_TRANSCRIPT_CHARS = 200_000
MIN_DICTATION_WORDS = 6


def _connect() -> sqlite3.Connection:
    db = settings.wispr_dir / "flow.sqlite"
    if not db.exists():
        raise FileNotFoundError(f"Wispr Flow database not found at {db}")
    conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def _ts(v) -> datetime | None:
    """Wispr stores '2026-10-13 06:30:00.000 +00:00' strings and epoch-ms integers."""
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)) or str(v).isdigit():
        n = int(v)
        return datetime.fromtimestamp(n / 1000 if n > 10**11 else n, tz=timezone.utc)
    s = str(v).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S.%f %z", "%Y-%m-%d %H:%M:%S %z"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _since_str(since: datetime) -> str:
    # Same format Wispr uses, so string comparison in SQL works.
    return since.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.000 +00:00")


def _plain(text: str | None) -> str:
    if not text:
        return ""
    if "<" in text and ">" in text:
        text = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</h\d>", "\n", text)
        text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def _speaker_names(raw: str | None) -> dict[str, str]:
    try:
        data = json.loads(raw or "")
    except ValueError:
        return {}
    if isinstance(data, dict):
        return {str(k): (v.get("name") if isinstance(v, dict) else str(v)) or "" for k, v in data.items()}
    return {}


def _transcript(meeting_id: str, speakers: dict[str, str]) -> str:
    folder = settings.wispr_dir / "meetings" / meeting_id
    for name in ("refined.ndjson", "live.ndjson"):  # refined = cleaned-up version
        path = folder / name
        if not path.exists():
            continue
        turns: list[list[str]] = []
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            text = (rec.get("text") or "").strip()
            if not text:
                continue
            sp = rec.get("speaker") or {}
            sid = str(sp.get("id", "")) if isinstance(sp, dict) else str(sp)
            who = (sp.get("name") if isinstance(sp, dict) else None) or speakers.get(sid) or f"Speaker {sid or '?'}"
            if turns and turns[-1][0] == who:
                turns[-1][1] += " " + text
            else:
                turns.append([who, text])
        if turns:
            out = "\n".join(f"{w}: {t}" for w, t in turns)
            if len(out) > MAX_TRANSCRIPT_CHARS:
                print(f"[wispr] transcript {meeting_id} truncated from {len(out)} chars")
                out = out[:MAX_TRANSCRIPT_CHARS] + "\n[...truncated]"
            return out
    return ""


def _meetings(conn: sqlite3.Connection, since: datetime) -> list[SourceItem]:
    since_ms = int(since.timestamp() * 1000)
    rows = conn.execute(
        """select * from Meetings
           where coalesce(isDeleted, 0) = 0
             and (modifiedAt >= ? or coalesce(endedAt, 0) >= ?)""",
        (_since_str(since), since_ms),
    ).fetchall()
    items = []
    for m in rows:
        if not m["endedAt"]:
            continue  # still recording
        ended = _ts(m["endedAt"])
        started = _ts(m["createdAt"]) or ended
        todos = conn.execute(
            "select title, status from Todos where meetingId = ? and coalesce(isDeleted, 0) = 0 "
            "order by sortOrder", (m["id"],),
        ).fetchall()
        participants = m["participantNames"] or ""
        if m["calendarEventExternalId"]:
            ev = conn.execute(
                "select title, participantNames from CalendarEvents where externalId = ?",
                (m["calendarEventExternalId"],),
            ).fetchone()
            if ev and not participants:
                participants = ev["participantNames"] or ""
        try:
            plist = json.loads(participants) if participants.strip()[:1] in "[{" else participants.split(",")
            plist = [p if isinstance(p, str) else (p.get("name") or p.get("email") or "") for p in plist]
        except (ValueError, AttributeError):
            plist = [participants]
        summary = _plain(m["summary"]) or _plain(m["candidateSummary"])
        body = "\n\n".join(x for x in [
            f"Wispr Flow meeting recording, {started.astimezone(settings.tz):%a %d %b %H:%M}"
            f"–{ended.astimezone(settings.tz):%H:%M} {settings.tz.key}",
            f"Summary:\n{summary}" if summary else "",
            f"My notes:\n{_plain(m['notes'])}" if m["notes"] else "",
            "To-dos:\n" + "\n".join(f"- [{t['status'] or 'open'}] {t['title']}" for t in todos) if todos else "",
            "Transcript:\n" + (_transcript(m["id"], _speaker_names(m["speakerMap"])) or "(not available)"),
        ] if x)
        items.append(SourceItem(
            source="wispr",
            # Processed once when it ends, and once more when the AI summary lands.
            ref=f"meeting:{m['id']}:{'summary' if summary else 'raw'}",
            timestamp=started,
            title=m["title"] or "Untitled meeting",
            author=settings.me_name,
            participants=[p.strip() for p in plist if p and p.strip()],
            body=body,
        ))
    return items


def _notes(conn: sqlite3.Connection, since: datetime) -> list[SourceItem]:
    rows = conn.execute(
        "select id, title, content, searchableContent, createdAt, modifiedAt from Notes "
        "where coalesce(isDeleted, 0) = 0 and modifiedAt >= ?",
        (_since_str(since),),
    ).fetchall()
    return [
        SourceItem(
            source="wispr",
            ref=f"note:{n['id']}@{n['modifiedAt']}",
            timestamp=_ts(n["modifiedAt"]) or _ts(n["createdAt"]),
            title=f"Note: {n['title'] or 'Untitled'}",
            author=settings.me_name,
            body=_plain(n["searchableContent"]) or _plain(n["content"]),
        )
        for n in rows
        if (n["searchableContent"] or n["content"])
    ]


def _dictations(conn: sqlite3.Connection, since: datetime) -> list[SourceItem]:
    rows = conn.execute(
        "select transcriptEntityId, timestamp, app, url, editedText, formattedText, asrText, numWords "
        "from History where timestamp >= ? and coalesce(isArchived, 0) = 0 order by timestamp",
        (_since_str(since),),
    ).fetchall()
    items = []
    for r in rows:
        text = (r["editedText"] or r["formattedText"] or r["asrText"] or "").strip()
        if len(text.split()) < MIN_DICTATION_WORDS:
            continue
        items.append(SourceItem(
            source="wispr",
            ref=f"dictation:{r['transcriptEntityId']}",
            timestamp=_ts(r["timestamp"]),
            title=f"Dictated by me into {r['app'] or 'an app'}",
            author=settings.me_name,
            body=text + (f"\n(App: {r['app']}{', ' + r['url'] if r['url'] else ''})"),
        ))
    return items


def fetch(since: datetime) -> list[SourceItem]:
    conn = _connect()
    try:
        items = _meetings(conn, since)
        if settings.wispr_include_notes:
            items += _notes(conn, since)
        if settings.wispr_include_dictations:
            items += _dictations(conn, since)
    finally:
        conn.close()
    items = [i for i in items if i.timestamp]
    items.sort(key=lambda i: i.timestamp)
    return items
