"""Claude extraction: raw items + currently-open items -> Extraction."""
from __future__ import annotations

import json
from datetime import datetime

import anthropic

from .config import settings
from .models import Extraction
from .sources import SourceItem

# Keep each request comfortably sized; open items are re-sent per batch so
# later batches can close items opened by earlier ones.
BATCH_CHARS = 250_000

SYSTEM = """You are the chief of staff for {me}, CEO of a real estate company (Alcove Realty, India). \
You read the CEO's raw communications and maintain a ledger of what matters.

The CEO's email addresses: {emails}.

Extract only real business signal. Ignore newsletters, marketing, automated notifications, \
OTPs and receipts unless they reveal a deadline, payment due or risk.

Definitions:
- Commitment: someone (the CEO, staff, a vendor, a buyer, a broker, a bank) promised to do \
something. "I'll send the drawings by Friday" is a commitment owned by the sender. A request \
the CEO accepted ("Sure, will do") is a commitment owned by the CEO. Mark status Done only \
if the same item shows it already happened.
- Decision: something was decided or agreed (pricing, vendor chosen, plan approved, date fixed).
- Risk: anything that could hurt a project, deal, cash flow, compliance (RERA, approvals, \
permits), legal position, or reputation: delays, cost overruns, disputes, unhappy buyers, \
payment defaults, regulatory notices.
- Approval: someone is waiting on the CEO to approve, sign, decide, release payment or reply \
before they can proceed. Only include items where the CEO has not yet acted.

Ledger rules:
- You are given the currently OPEN commitments and PENDING approvals with IDs. If a new item \
refers to one of them, do NOT create a duplicate. Instead emit a commitment_update / \
approval_update with that ID when the status or due date changed (e.g. the file was sent, \
the CEO approved, the deadline moved). If nothing changed, emit nothing for it.
- If the CEO replied approving/declining something, close the approval via approval_updates.
- Resolve relative dates ("tomorrow", "by Friday", "end of month") against the item's \
timestamp, in the {tz} timezone, to YYYY-MM-DD.
- Calendar items: an invite being scheduled is evidence that a commitment to set up that meeting is Done. Agendas/notes may contain decisions or commitments. Do not create a commitment merely because a meeting exists or someone is attending it.
- Wispr Flow meeting items are recordings the CEO made: summary, notes, to-dos and a \
transcript. Speakers may be unlabelled ("Speaker 1"); infer who is who from context and \
participants where you reasonably can, else name the owner "Unassigned (<meeting title>)". \
Spoken promises ("I'll get you the revised layout by Thursday") are commitments. Wispr \
dictation items are text the CEO spoke into another app, e.g. a reply or message they sent.
- WhatsApp items are chats from the CEO's phone. "+91... (name unknown)" means the contact isn't in the ledger yet: if the chat reveals who it is, add them to people with that phone. In groups the individual sender isn't known; attribute carefully or use "Unassigned (<group>)".
- Use consistent project names (prefer the names already present in the ledger).
- Use people's full names as written in signatures/headers; use "{me}" for the CEO.
- Evidence: a short verbatim quote (under 25 words).
- source_ref must be the exact ref attribute of the item.
- Return empty lists when there is nothing to report. Never invent items."""


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env


def _batches(items: list[SourceItem]) -> list[list[SourceItem]]:
    out, cur, size = [], [], 0
    for it in items:
        txt = len(it.render())
        if cur and size + txt > BATCH_CHARS:
            out.append(cur)
            cur, size = [], 0
        cur.append(it)
        size += txt
    if cur:
        out.append(cur)
    return out


def extract(
    items: list[SourceItem], open_ledger: dict, now: datetime, on_batch=None
) -> list[Extraction]:
    """Run extraction batch by batch.

    `open_ledger` is a dict with "commitments", "approvals", "projects" lists.
    `on_batch(extraction, batch_items)` is called after each successful batch
    so the caller can merge, mark items processed, and return a refreshed
    `open_ledger` for the next batch. Skipped batches are retried next run.
    """
    client = _client()
    system = SYSTEM.format(
        me=settings.me_name,
        emails=", ".join(settings.me_emails) or "(not set)",
        tz=settings.tz.key,
    )
    results: list[Extraction] = []
    batches = _batches(items)
    for n, batch in enumerate(batches, 1):
        print(f"[claude] batch {n}/{len(batches)}: {len(batch)} items")
        user = (
            f"Today is {now.strftime('%A %Y-%m-%d %H:%M')} ({settings.tz.key}).\n\n"
            "<ledger>\n"
            + json.dumps(open_ledger, ensure_ascii=False, indent=1, default=str)
            + "\n</ledger>\n\n<items>\n"
            + "\n\n".join(i.render() for i in batch)
            + "\n</items>\n\nExtract the ledger changes from these items."
        )
        try:
            resp = client.beta.messages.parse(
                model=settings.claude_model,
                max_tokens=16000,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_config={"effort": settings.claude_effort},
                output_format=Extraction,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except anthropic.RateLimitError as e:
            raise RuntimeError(f"Claude rate limit hit; rerun later ({e.message})") from e
        except anthropic.APIStatusError as e:
            raise RuntimeError(f"Claude API error {e.status_code}: {e.message}") from e

        if resp.stop_reason == "refusal":
            print(f"[claude] batch {n} declined ({getattr(resp.stop_details, 'category', None)}); skipped")
            continue
        if resp.stop_reason == "max_tokens" or resp.parsed_output is None:
            print(f"[claude] batch {n} hit max_tokens / unparsable output; skipped")
            continue

        result = resp.parsed_output
        results.append(result)
        if on_batch:
            open_ledger = on_batch(result, batch) or open_ledger
    return results
