"""Settings loaded from .env (never hard-code secrets)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _get(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _path(name: str, default: str) -> Path:
    p = Path(_get(name, default))
    return p if p.is_absolute() else ROOT / p


@dataclass(frozen=True)
class Settings:
    me_name: str = field(default_factory=lambda: _get("ME_NAME", "Me"))
    me_emails: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            e.strip().lower() for e in _get("ME_EMAILS").split(",") if e.strip()
        )
    )
    tz: ZoneInfo = field(default_factory=lambda: ZoneInfo(_get("TIMEZONE", "Asia/Kolkata")))

    claude_model: str = field(default_factory=lambda: _get("CLAUDE_MODEL", "claude-opus-5-5"))
    claude_effort: str = field(default_factory=lambda: _get("CLAUDE_EFFORT", "high"))

    google_client_secrets: Path = field(
        default_factory=lambda: _path("GOOGLE_CLIENT_SECRETS", "secrets/credentials.json")
    )
    google_token_file: Path = field(
        default_factory=lambda: _path("GOOGLE_TOKEN_FILE", "secrets/token.json")
    )
    gmail_query: str = field(
        default_factory=lambda: _get("GMAIL_QUERY", "-category:promotions -category:social")
    )
    gmail_max_messages: int = field(default_factory=lambda: int(_get("GMAIL_MAX_MESSAGES", "300")))
    calendar_ids: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            c.strip() for c in _get("CALENDAR_IDS", "primary").split(",") if c.strip()
        )
    )

    wispr_dir: Path = field(
        default_factory=lambda: Path(
            _get("WISPR_DIR") or Path(os.getenv("APPDATA", "")) / "Wispr Flow"
        )
    )
    wispr_include_notes: bool = field(default_factory=lambda: _get("WISPR_INCLUDE_NOTES", "true").lower() == "true")
    wispr_include_dictations: bool = field(
        default_factory=lambda: _get("WISPR_INCLUDE_DICTATIONS", "false").lower() == "true"
    )

    # Everything persistent lives under DATA_DIR. In cloud mode this is the
    # brain-data branch worktree (.brain-data/data); see scripts/brain_data.sh.
    data_dir: Path = field(default_factory=lambda: _path("DATA_DIR", "data"))
    master_xlsx: Path = field(
        default_factory=lambda: _path("MASTER_XLSX", str(_path("DATA_DIR", "data") / "second_brain.xlsx"))
    )
    dashboard_html: Path = field(
        default_factory=lambda: _path("DASHBOARD_HTML", "output/dashboard.html")
    )
    state_file: Path = field(default_factory=lambda: _path("DATA_DIR", "data") / "state.json")
    lookback_hours: int = field(default_factory=lambda: int(_get("LOOKBACK_HOURS", "24")))

    me_phone: str = field(default_factory=lambda: _get("ME_PHONE"))
    # Read chats through the claude.ai WhatsApp connector (headless Claude Code)
    whatsapp_sync: bool = field(default_factory=lambda: _get("WHATSAPP_SYNC", "true").lower() == "true")
    # How to send the morning summary: claude (your own number, via the connector) | cloudapi | none
    whatsapp_send_via: str = field(default_factory=lambda: _get("WHATSAPP_SEND_VIA", "claude").lower())
    claude_cli: str = field(default_factory=lambda: _get("CLAUDE_CLI"))
    claude_cli_model: str = field(default_factory=lambda: _get("CLAUDE_CLI_MODEL"))

    whatsapp_token: str = field(default_factory=lambda: _get("WHATSAPP_TOKEN"))
    whatsapp_phone_number_id: str = field(default_factory=lambda: _get("WHATSAPP_PHONE_NUMBER_ID"))
    whatsapp_to: str = field(default_factory=lambda: _get("WHATSAPP_TO"))
    whatsapp_template_name: str = field(default_factory=lambda: _get("WHATSAPP_TEMPLATE_NAME"))
    whatsapp_template_lang: str = field(default_factory=lambda: _get("WHATSAPP_TEMPLATE_LANG", "en"))

    @property
    def whatsapp_enabled(self) -> bool:
        return bool(self.whatsapp_token and self.whatsapp_phone_number_id and self.whatsapp_to)


settings = Settings()
