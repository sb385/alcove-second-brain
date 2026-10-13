"""Gmail connector (read-only; OAuth in google_auth.py)."""
from __future__ import annotations

import base64
import html
import re
from datetime import datetime, timezone
from email.utils import getaddresses, parsedate_to_datetime

from googleapiclient.discovery import build

from ..config import settings
from .base import SourceItem
from .google_auth import get_credentials

# Per-email cap after quoted history is stripped. Long newsletters/legal
# drafts beyond this are rarely where commitments live; the cut is logged.
MAX_BODY_CHARS = 15_000

_QUOTE_MARKERS = [
    re.compile(r"^On .{5,200}wrote:\s*$", re.M),
    re.compile(r"^-{2,}\s*Original Message\s*-{2,}", re.M | re.I),
    re.compile(r"^-{2,}\s*Forwarded message\s*-{2,}", re.M | re.I),
    re.compile(r"^From: .+\nSent: .+", re.M),
]


def _decode(data: str) -> str:
    return base64.urlsafe_b64decode(data.encode()).decode("utf-8", errors="replace")


def _html_to_text(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style|head).*?</\1>", " ", raw)
    raw = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>|</li>", "\n", raw)
    raw = re.sub(r"<[^>]+>", " ", raw)
    raw = html.unescape(raw)
    raw = re.sub(r"[ \t\xa0]+", " ", raw)
    return re.sub(r"\n\s*\n+", "\n\n", raw).strip()


def _extract_body(payload: dict) -> str:
    plain, rich = [], []

    def walk(part: dict) -> None:
        mime = part.get("mimeType", "")
        data = part.get("body", {}).get("data")
        if part.get("filename"):
            return  # attachment
        if data and mime == "text/plain":
            plain.append(_decode(data))
        elif data and mime == "text/html":
            rich.append(_html_to_text(_decode(data)))
        for sub in part.get("parts", []) or []:
            walk(sub)

    walk(payload)
    return "\n".join(plain) if plain else "\n".join(rich)


def _strip_quoted(text: str) -> str:
    cut = len(text)
    for pat in _QUOTE_MARKERS:
        m = pat.search(text)
        if m and m.start() > 0:
            cut = min(cut, m.start())
    text = text[:cut]
    lines = [ln for ln in text.splitlines() if not ln.lstrip().startswith(">")]
    return "\n".join(lines).strip()


def _attachments(payload: dict) -> list[str]:
    names = []

    def walk(part: dict) -> None:
        if part.get("filename"):
            names.append(part["filename"])
        for sub in part.get("parts", []) or []:
            walk(sub)

    walk(payload)
    return names


def fetch(since: datetime) -> list[SourceItem]:
    service = build("gmail", "v1", credentials=get_credentials(), cache_discovery=False)
    query = f"after:{int(since.timestamp())} {settings.gmail_query}".strip()

    ids: list[str] = []
    page_token = None
    while len(ids) < settings.gmail_max_messages:
        resp = (
            service.users()
            .messages()
            .list(userId="me", q=query, pageToken=page_token, maxResults=100)
            .execute()
        )
        ids += [m["id"] for m in resp.get("messages", [])]
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    if len(ids) > settings.gmail_max_messages:
        print(f"[gmail] {len(ids)} messages matched; capped at {settings.gmail_max_messages}")
        ids = ids[: settings.gmail_max_messages]

    items: list[SourceItem] = []
    for mid in ids:
        msg = service.users().messages().get(userId="me", id=mid, format="full").execute()
        payload = msg.get("payload", {})
        headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}

        try:
            ts = parsedate_to_datetime(headers.get("date", ""))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            ts = datetime.fromtimestamp(int(msg["internalDate"]) / 1000, tz=timezone.utc)

        body = _strip_quoted(_extract_body(payload)) or msg.get("snippet", "")
        if len(body) > MAX_BODY_CHARS:
            print(f"[gmail] body of {mid} truncated from {len(body)} chars")
            body = body[:MAX_BODY_CHARS] + "\n[...truncated]"
        atts = _attachments(payload)
        if atts:
            body += "\n\nAttachments: " + ", ".join(atts)

        recipients = getaddresses(
            [headers.get("to", ""), headers.get("cc", "")]
        )
        labels = msg.get("labelIds", [])
        items.append(
            SourceItem(
                source="gmail",
                ref=mid,
                timestamp=ts,
                title=headers.get("subject", "(no subject)")
                + (" [SENT BY ME]" if "SENT" in labels else ""),
                author=headers.get("from", ""),
                participants=[f"{n} <{a}>" if n else a for n, a in recipients if a],
                body=body,
                link=f"https://mail.google.com/mail/u/0/#all/{msg['threadId']}",
            )
        )
    items.sort(key=lambda i: i.timestamp)
    return items
