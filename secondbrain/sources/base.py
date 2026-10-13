from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class SourceItem:
    """One unit of raw input (an email, a chat message, a meeting, a transcript)."""

    source: str          # "gmail", "calendar", "whatsapp", "fireflies"
    ref: str             # stable id within the source, e.g. Gmail message id
    timestamp: datetime  # timezone-aware
    title: str           # subject / chat name / meeting title
    author: str          # sender / organiser / speaker
    participants: list[str] = field(default_factory=list)
    body: str = ""
    link: str = ""       # deep link back to the original

    @property
    def key(self) -> str:
        return f"{self.source}:{self.ref}"

    def render(self) -> str:
        return (
            f"<item ref=\"{self.key}\" source=\"{self.source}\" "
            f"time=\"{self.timestamp.isoformat()}\">\n"
            f"Title: {self.title}\n"
            f"From: {self.author}\n"
            f"Participants: {', '.join(self.participants)}\n\n"
            f"{self.body.strip()}\n"
            f"</item>"
        )
