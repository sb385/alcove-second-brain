"""Shared Google OAuth for Gmail + Calendar (read-only)."""
from __future__ import annotations

import sys

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from ..config import settings

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
]

_creds: Credentials | None = None


def get_credentials(interactive: bool | None = None) -> Credentials:
    """Load the saved token; refresh it, or run browser consent if allowed.

    Consent is needed on first use and whenever SCOPES grows (e.g. a new
    Google source was added). The scheduled task can't click through a
    browser, so it fails fast and asks you to run `--auth` instead.
    """
    global _creds
    if _creds and _creds.valid:
        return _creds
    if interactive is None:
        interactive = sys.stdin is not None and sys.stdin.isatty()

    token_path = settings.google_token_file
    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path))
        if not creds.has_scopes(SCOPES):
            creds = None  # token predates a newly added scope

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    elif not (creds and creds.valid):
        if not interactive:
            raise RuntimeError(
                "Google sign-in needed (new or missing permissions). Run once by hand: "
                "python -m secondbrain.main --auth"
            )
        if not settings.google_client_secrets.exists():
            raise FileNotFoundError(
                f"Google OAuth client file not found at {settings.google_client_secrets}. "
                "See README → 'Gmail setup'."
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(settings.google_client_secrets), SCOPES)
        creds = flow.run_local_server(port=0)

    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json(), encoding="utf-8")
    _creds = creds
    return creds
