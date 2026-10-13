"""Google Calendar connector (read-only; OAuth in google_auth.py).

Two uses:
- fetch(since): meetings that just happened or were newly scheduled/moved, fed
  to Claude so it can spot decisions in agendas/notes and close commitments
  like "set up a call with the bank" once the invite exists.
- upcoming(now): the next 7 days for the dashboard's meetings section.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from googleapiclient.discovery import build

from ..config import settings
from .base import SourceItem
from .google_auth import get_credentials

MAX_DESC_CHARS = 8_000


@dataclass
class Attendee:
    name: str
    email: str
    response: str  # accepted / declined / tentative / needsAction


@dataclass
class Meeting:
    id: str
    title: str
    start: datetime
    end: datetime
    all_day: bool
    organizer: str
    attendees: list[Attendee] = field(default_factory=list)
    location: str = ""
    join_link: str = ""
    link: str = ""
    description: str = ""
    my_response: str = ""
    updated: str = ""

    @property
    def others(self) -> list[Attendee]:
        return [a for a in self.attendees if a.email.lower() not in settings.me_emails]


def _service():
    return build("calendar", "v3", credentials=get_credentials(), cache_discovery=False)


def _parse_time(t: dict) -> tuple[datetime, bool]:
    if "dateTime" in t:
        return datetime.fromisoformat(t["dateTime"].replace("Z", "+00:00")).astimezone(settings.tz), False
    d = datetime.fromisoformat(t["date"])
    return d.replace(tzinfo=settings.tz), True


def _to_meeting(ev: dict) -> Meeting | None:
    if ev.get("status") == "cancelled":
        return None
    if ev.get("eventType", "default") not in ("default", "fromGmail"):
        return None  # out-of-office, focus time, working location
    start, all_day = _parse_time(ev["start"])
    end, _ = _parse_time(ev["end"])
    attendees = [
        Attendee(a.get("displayName") or a.get("email", ""), a.get("email", ""),
                 a.get("responseStatus", ""))
        for a in ev.get("attendees", [])
        if not a.get("resource")  # skip meeting rooms
    ]
    mine = next((a.get("responseStatus", "") for a in ev.get("attendees", []) if a.get("self")), "accepted")
    if mine == "declined":
        return None
    if all_day and not attendees:
        return None  # holidays, reminders, birthdays
    join = ev.get("hangoutLink", "")
    for ep in ev.get("conferenceData", {}).get("entryPoints", []):
        if ep.get("entryPointType") == "video":
            join = ep.get("uri", join)
    org = ev.get("organizer", {})
    return Meeting(
        id=ev["id"], title=ev.get("summary", "(no title)"), start=start, end=end,
        all_day=all_day, organizer=org.get("displayName") or org.get("email", ""),
        attendees=attendees, location=ev.get("location", ""), join_link=join,
        link=ev.get("htmlLink", ""), description=(ev.get("description") or "")[:MAX_DESC_CHARS],
        my_response=mine, updated=ev.get("updated", ""),
    )


def _list(time_min: datetime, time_max: datetime, updated_min: datetime | None = None) -> list[Meeting]:
    svc = _service()
    out: list[Meeting] = []
    for cal_id in settings.calendar_ids:
        page = None
        while True:
            kw = dict(
                calendarId=cal_id, timeMin=time_min.isoformat(), timeMax=time_max.isoformat(),
                singleEvents=True, orderBy="startTime", maxResults=250, pageToken=page,
            )
            if updated_min:
                kw["updatedMin"] = updated_min.isoformat()
            resp = svc.events().list(**kw).execute()
            out += [m for ev in resp.get("items", []) if (m := _to_meeting(ev))]
            page = resp.get("nextPageToken")
            if not page:
                break
    out.sort(key=lambda m: m.start)
    return out


def _as_item(m: Meeting, note: str) -> SourceItem:
    when = "All day" if m.all_day else f"{m.start:%a %d %b %H:%M}–{m.end:%H:%M}"
    people = "\n".join(f"- {a.name} <{a.email}> ({a.response})" for a in m.attendees)
    body = (
        f"[{note}] Meeting: {when} {settings.tz.key}\n"
        f"Organizer: {m.organizer}\nLocation: {m.location or '-'}\n"
        f"Attendees:\n{people or '- none'}\n\nDescription/agenda:\n{m.description or '-'}"
    )
    return SourceItem(
        source="calendar",
        ref=f"{m.id}@{m.updated}",  # a rescheduled/edited event is re-read
        timestamp=m.start,
        title=m.title,
        author=m.organizer,
        participants=[f"{a.name} <{a.email}>" for a in m.attendees],
        body=body,
        link=m.link,
    )


def fetch(since: datetime) -> list[SourceItem]:
    now = datetime.now(settings.tz)
    items: dict[str, SourceItem] = {}
    # Meetings that took place in the window.
    for m in _list(since, now):
        if m.end <= now:
            items[m.id] = _as_item(m, "Held")
    # Upcoming meetings created or changed in the window (new invites, reschedules).
    for m in _list(now, now + timedelta(days=30), updated_min=since):
        items.setdefault(m.id, _as_item(m, "Newly scheduled or updated"))
    return sorted(items.values(), key=lambda i: i.timestamp)


def upcoming(now: datetime, days: int = 7) -> list[Meeting]:
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return [m for m in _list(start, start + timedelta(days=days)) if not m.all_day or m.attendees]
