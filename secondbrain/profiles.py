"""Business profiles (dashboard tabs). Every commitment, decision, risk,
approval and source message is tagged with exactly one profile name.

Edit names/aliases here; aliases are lowercase words or phrases that identify
the profile in a project name or text (used to tag older rows and meetings).
"""
from __future__ import annotations

import re

PROFILES: list[dict] = [
    {"key": "triveni", "name": "Triveni Mall", "aliases": ["triveni", "trivani"]},
    {"key": "sangam", "name": "Sangam", "aliases": ["sangam", "sangeam"]},
    {"key": "sundarban", "name": "Sundarban", "aliases": ["sundarban", "sundarbun", "sunderban"]},
    {"key": "adllp", "name": "ADLLP & Group",
     "aliases": ["adllp", "alcove developers", "alcove group", "group compan"]},
    {"key": "caliber", "name": "Caliber", "aliases": ["caliber", "calibre"]},
    {"key": "personal", "name": "Personal", "aliases": ["personal", "family"]},
    {"key": "other", "name": "Other", "aliases": []},
]
NAMES = tuple(p["name"] for p in PROFILES)
KEY_BY_NAME = {p["name"]: p["key"] for p in PROFILES}
OTHER = "Other"

# Guidance for Claude, kept next to the list so they never drift apart.
GUIDE = """Profiles (pick exactly one per item, using these exact names):
- Triveni Mall: the Triveni Mall project (leasing, tenants, mall operations, its approvals and vendors).
- Sangam: the Sangam project (towers, clubhouse, buyers, snags, its contractors).
- Sundarban: the Sundarban project.
- ADLLP & Group: Alcove Developers LLP and the other Alcove group companies, and
  company-level matters (finance, banking, legal, HR, accounts) that aren't tied to one project.
- Caliber: anything related to Caliber.
- Personal: the CEO's personal and family matters.
- Other: only when none of the above fits."""


def guess(*texts) -> str:
    """Best-effort profile from free text (project names, titles). Falls back to Other."""
    blob = " ".join(str(t or "") for t in texts).lower()
    for p in PROFILES:
        if any(re.search(rf"\b{re.escape(a)}", blob) for a in p["aliases"]):
            return p["name"]
    return OTHER


def key(name: str | None) -> str:
    return KEY_BY_NAME.get(name or OTHER, "other")
