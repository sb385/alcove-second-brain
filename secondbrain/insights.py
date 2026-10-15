"""Views over the ledger shared by the dashboard and the WhatsApp summary."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from .config import settings
from .store import OPEN_APPROVAL, OPEN_COMMITMENT, Store, norm


@dataclass
class Action:
    kind: str        # "Approval", "My commitment", "Risk"
    id: str
    text: str
    who: str
    due: str | None
    project: str | None
    link: str | None
    score: int
    flag: str        # "Overdue", "Due today", "New", ...
    profile: str = "Other"


def is_me(owner, email=None) -> bool:
    if email and str(email).lower() in settings.me_emails:
        return True
    o = norm(owner)
    return bool(o) and (o == norm(settings.me_name) or o in {"me", "ceo"})


def _days(d, today: date) -> int | None:
    try:
        return (date.fromisoformat(str(d)[:10]) - today).days
    except ValueError:
        return None


def _age(stamp, today: date) -> int:
    d = _days(stamp, today)
    return -d if d is not None else 0


def waiting_on_me(store: Store, today: date) -> list[Action]:
    out = []
    for r in store.rows["Approvals"]:
        if r.get("Status") not in OPEN_APPROVAL:
            continue
        dd = _days(r.get("Due"), today)
        age = _age(r.get("First Seen"), today)
        score = 50 + min(age * 3, 24)
        flag = f"Waiting {age}d" if age else "New"
        if dd is not None and dd < 0:
            score, flag = score + 30, "Overdue"
        elif dd == 0:
            score, flag = score + 20, "Due today"
        out.append(Action("Approval", r["ID"], r.get("Item", ""), r.get("Requested By", ""),
                          r.get("Due"), r.get("Project"), r.get("Source Link"), score, flag,
                          r.get("Profile") or "Other"))
    for r in store.rows["Commitments"]:
        if r.get("Status") not in OPEN_COMMITMENT or not is_me(r.get("Owner"), r.get("Owner Email")):
            continue
        dd = _days(r.get("Due"), today)
        score, flag = 20, "Open"
        if dd is not None and dd < 0:
            score, flag = 45 + min(-dd * 2, 20), f"Overdue {-dd}d"
        elif dd == 0:
            score, flag = 40, "Due today"
        elif dd is not None and dd <= 2:
            score, flag = 25, f"Due in {dd}d"
        out.append(Action("My commitment", r["ID"], r.get("Item", ""), settings.me_name,
                          r.get("Due"), r.get("Project"), r.get("Source Link"), score, flag,
                          r.get("Profile") or "Other"))
    return sorted(out, key=lambda a: -a.score)


def new_high_risks(store: Store, now: datetime) -> list[Action]:
    since = (now - timedelta(hours=settings.lookback_hours + 1)).strftime("%Y-%m-%d %H:%M")
    return [
        Action("Risk", r["ID"], r.get("Risk", ""), r.get("Owner") or "", None, r.get("Project"),
               r.get("Source Link"), 42, "New · High", r.get("Profile") or "Other")
        for r in store.rows["Risks"]
        if r.get("Status", "Open") == "Open" and r.get("Severity") == "High"
        and str(r.get("First Seen") or "") >= since
    ]


def act_today(store: Store, now: datetime) -> list[Action]:
    today = now.date()
    # Overdue / due today, plus approvals that have waited 2+ days (score >= 56).
    urgent = [
        a for a in waiting_on_me(store, today)
        if a.flag.startswith(("Overdue", "Due today")) or (a.kind == "Approval" and a.score >= 56)
    ]
    out = {a.id: a for a in urgent + new_high_risks(store, now)}
    for a in follow_ups_due(store, today):  # a follow-up date always brings the item back
        out[a.id] = a
    return sorted(out.values(), key=lambda a: -a.score)


def follow_ups_due(store: Store, today: date) -> list[Action]:
    """Open items whose dashboard follow-up date has arrived."""
    out = []
    sheets = (("Commitments", "Item", OPEN_COMMITMENT, "Commitment"),
              ("Approvals", "Item", OPEN_APPROVAL, "Approval"),
              ("Risks", "Risk", {"Open"}, "Risk"),
              ("Tasks", "Work", {"Open", "Blocked"}, "Task"))
    for sheet, col, open_states, kind in sheets:
        for r in store.rows[sheet]:
            fu = _days(r.get("Follow Up"), today)
            if fu is None or fu > 0 or r.get("Status", "Open") not in open_states:
                continue
            who = r.get("Owner") or r.get("Requested By") or ""
            flag = "Follow up" if fu == 0 else f"Follow up · {-fu}d ago"
            out.append(Action(kind, r["ID"], r.get(col, ""), who, r.get("Due"), r.get("Project"),
                              r.get("Source Link"), 48 + min(-fu * 2, 10), flag, r.get("Profile") or "Other"))
    return out


def overdue_by_owner(store: Store, today: date) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in store.rows["Commitments"]:
        if r.get("Status") in OPEN_COMMITMENT:
            dd = _days(r.get("Due"), today)
            if dd is not None and dd < 0:
                groups[r.get("Owner") or "Unassigned"].append({**r, "_late": -dd})
    for rows in groups.values():
        rows.sort(key=lambda r: -r["_late"])
    return dict(sorted(groups.items(), key=lambda kv: -len(kv[1])))


def meeting_prep(store: Store, attendees) -> list[str]:
    """Open items involving any of a meeting's attendees, e.g. 'A-0003 Approve steel PO'."""
    emails = {a.email.lower() for a in attendees if a.email}
    names = {norm(a.name) for a in attendees if a.name}
    # People sheet lets us map an attendee's email to the name used in the ledger
    for p in store.rows["People"]:
        if str(p.get("Email") or "").lower() in emails:
            names.add(norm(p.get("Name")))
    names.discard("")

    def involved(name, email) -> bool:
        return (email and str(email).lower() in emails) or (norm(name) in names)

    out = []
    for r in store.rows["Approvals"]:
        if r.get("Status") in OPEN_APPROVAL and involved(r.get("Requested By"), r.get("Requested By Email")):
            out.append(f"{r['ID']} approval: {r.get('Item')}")
    for r in store.rows["Commitments"]:
        if r.get("Status") in OPEN_COMMITMENT and involved(r.get("Owner"), r.get("Owner Email")):
            due = f" (due {r['Due']})" if r.get("Due") else ""
            out.append(f"{r['ID']} {r.get('Owner')}: {r.get('Item')}{due}")
    return out


def top_items(store: Store, now: datetime, n: int = 5) -> list[Action]:
    seen, out = set(), []
    for a in act_today(store, now) + waiting_on_me(store, now.date()):
        if a.id not in seen:
            seen.add(a.id)
            out.append(a)
    return out[:n]
