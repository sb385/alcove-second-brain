"""Source connectors. Each returns a list of SourceItem for a time window.

To add a source (Calendar, WhatsApp, Fireflies), add a module with a
`fetch(since: datetime) -> list[SourceItem]` function and register it in
SOURCES in secondbrain/main.py.
"""
from .base import SourceItem

__all__ = ["SourceItem"]
