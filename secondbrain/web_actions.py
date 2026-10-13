"""Apply dashboard clicks (Close / Follow up / Move / Shift) to the Excel ledger.

    python -m secondbrain.web_actions        # pull, apply, save, acknowledge

Run at the start of every sync, by publish.py before uploading, and by the
pre-push hook (a push redeploys the site and wipes queued clicks).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime

import requests

from .config import settings
from .store import Store

SHEET = {"C": "Commitments", "A": "Approvals", "R": "Risks"}
CLOSED = {"Commitments": "Done", "Approvals": "Done", "Risks": "Closed"}
LOG = "web_actions_applied.jsonl"  # local audit trail of every applied click


def _conn() -> tuple[str, dict] | None:
    url = os.getenv("PUBLISH_URL", "").rstrip("/")
    token = os.getenv("UPLOAD_TOKEN", "")
    return (url, {"Authorization": f"Bearer {token}"}) if url and token else None


def apply(store: Store, actions: list[dict], now: datetime) -> list[str]:
    """Apply clicks to the ledger in order; returns the uids handled."""
    stamp = now.strftime("%Y-%m-%d %H:%M")
    handled = []
    for a in sorted(actions, key=lambda x: x.get("at", "")):
        handled.append(a["uid"])
        if a["action"] == "contact":
            _upsert_contact(store, a.get("value") or "", stamp)
            continue
        sheet = SHEET.get(a["item"][:1])
        row = store._by_id(sheet, a["item"]) if sheet else None
        if not row:
            continue
        kind, value = a["action"], a.get("value") or ""
        if kind == "done":
            row["Status"] = CLOSED[sheet]
            if sheet == "Commitments":
                row["Done On"] = now.date().isoformat()
            elif sheet == "Approvals":
                row["Resolved On"] = now.date().isoformat()
            note = "closed"
        elif kind == "followup":
            row["Follow Up"] = value
            note = f"follow up on {value}"
        elif kind == "move":
            row["Profile"] = value
            note = f"moved to {value}"
        elif kind == "shift" and sheet != "Risks":
            row["Due"] = value
            note = f"due date shifted to {value}"
        elif kind == "nudge":
            note = f"forwarded {value}"  # e.g. "on WhatsApp to Hena"
            if " to " in value:  # shows under that person in "Pending with team"
                who = value.split(" to ", 1)[1].strip()
                if row.get("Pushed To") != who or not row.get("Pushed On"):  # a reminder keeps the first date
                    row["Pushed On"] = a.get("at", "")[:10] or now.date().isoformat()
                row["Pushed To"] = who
        else:
            continue
        row["Notes"] = f"{row.get('Notes') or ''}\n[{stamp}] Dashboard: {note}".strip()
        if sheet != "Risks":  # risks track "Last Seen" instead
            row["Last Updated"] = stamp
    return handled


def _upsert_contact(store: Store, value: str, stamp: str) -> None:
    """'Name|phone|email' from the dashboard: add to People, or fill in a known person's gaps."""
    from .sources.whatsapp import norm_phone
    from .store import norm
    name, phone, email = (value.split("|") + ["", "", ""])[:3]
    name, phone, email = name.strip(), norm_phone(phone), email.strip().lower()
    if not name:
        return
    row = next((p for p in store.rows["People"]
                if norm(p.get("Name")) == norm(name)
                or (phone and norm_phone(p.get("Phone")) == phone)
                or (email and str(p.get("Email") or "").lower() == email)), None)
    if row is None:
        row = {"Name": name, "First Seen": stamp}
        store.rows["People"].append(row)
    if phone:
        row["Phone"] = "+" + phone
    if email:
        row["Email"] = email
    row["Last Seen"] = stamp
    row["Notes"] = f"{row.get('Notes') or ''}\n[{stamp}] Contact saved from dashboard".strip()


def sync(now: datetime | None = None) -> int:
    """Pull queued clicks, apply them, save the Excel, acknowledge. Returns count applied."""
    conn = _conn()
    if not conn:
        return 0
    url, headers = conn
    now = now or datetime.now(settings.tz)
    try:
        r = requests.get(f"{url}/api/actions", headers=headers, timeout=30)
        r.raise_for_status()
        actions = r.json().get("actions", [])
    except requests.RequestException as e:
        print(f"[web-actions] could not fetch clicks ({e})")
        return 0
    if not actions:
        return 0
    store = Store()
    handled = apply(store, actions, now)
    store.refresh_rollups(now.date())
    store.save()
    log = settings.data_dir / LOG
    with log.open("a", encoding="utf-8") as fh:
        for a in actions:
            fh.write(json.dumps({**a, "applied": now.isoformat(timespec="seconds")}) + "\n")
    try:
        requests.post(f"{url}/api/actions/ack", json={"uids": handled}, headers=headers, timeout=30)
    except requests.RequestException as e:
        print(f"[web-actions] applied but could not acknowledge ({e}); they'll be re-applied harmlessly")
    print(f"[web-actions] applied {len(handled)} dashboard click(s) to the Excel")
    return len(handled)


if __name__ == "__main__":
    sync()
    sys.exit(0)
