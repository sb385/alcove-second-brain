"""Run the Claude Code CLI headlessly to use connectors only Claude can reach
(the claude.ai WhatsApp connector). Used for WhatsApp sync and sending."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from .config import ROOT, settings


def find_cli() -> str:
    if settings.claude_cli:
        return settings.claude_cli
    found = shutil.which("claude")
    if found:
        return found
    # Bundled with the VS Code extension; pick the newest installed version.
    ext = Path(os.environ.get("USERPROFILE", "~")).expanduser() / ".vscode" / "extensions"
    bins = sorted(ext.glob("anthropic.claude-code-*/resources/native-binary/claude.exe"),
                  key=lambda p: p.stat().st_mtime)
    if bins:
        return str(bins[-1])
    raise FileNotFoundError("Claude Code CLI not found. Install it or set CLAUDE_CLI in .env")


def run(prompt: str, allowed_tools: list[str], max_turns: int, timeout: int = 900) -> str:
    cmd = [find_cli(), "-p", prompt, "--allowedTools", *allowed_tools, "--max-turns", str(max_turns)]
    if settings.claude_cli_model:
        cmd += ["--model", settings.claude_cli_model]
    proc = subprocess.run(
        cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=timeout,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"claude CLI exited {proc.returncode}: {(proc.stderr or proc.stdout)[-800:]}")
    return proc.stdout.strip()
