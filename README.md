# Alcove Second Brain

Every morning at 08:00 IST this job:

1. Pulls the last 24h of **Gmail**, **Google Calendar** (meetings held, plus new or rescheduled invites), **Wispr Flow** (meetings you recorded, with summary, notes, to-dos and transcript, plus notes you wrote in Flow) and **WhatsApp** (chats active in the window).
2. Uses Claude (`claude-opus-5-5`) to extract **commitments, decisions, risks, and approvals waiting on you**.
3. Merges them into `data/second_brain.xlsx` (sheets: Commitments, Decisions, Projects, People, Approvals, Risks) without creating duplicates, and marks items Done or Approved when an email shows they happened.
4. Writes `output/dashboard.html` with four sections: Act Today, Waiting on Me, Overdue by Owner, and This Week's Meetings. Each meeting lists the open items and approvals involving its attendees, so you walk in prepared.
5. Sends the top 5 items and a line about today's meetings to your own WhatsApp "message yourself" chat.

## One-time setup

### 1. Python
Install Python 3.12 with `winget install Python.Python.3.12`, then open a new terminal:

```powershell
cd D:\alcove-second-brain
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
copy .env.example .env      # then fill it in
```

### 2. Claude API key
Create a key at console.anthropic.com and put it in `.env` as `ANTHROPIC_API_KEY`.

### 3. Gmail + Calendar setup (Google OAuth)
1. Go to console.cloud.google.com and create a project, for example "Alcove Second Brain".
2. Under **APIs & Services → Library**, enable the **Gmail API** and the **Google Calendar API**.
3. Under **OAuth consent screen**, choose Internal if you're on Google Workspace. Otherwise choose External and add yourself as a test user.
4. Under **Credentials → Create credentials → OAuth client ID**, choose the **Desktop app** type and download the JSON file.
5. Save the file as `secrets/credentials.json`.
6. Run `.\.venv\Scripts\python -m secondbrain.main --auth`. A browser opens for you to approve read-only Gmail and Calendar access, and the token is saved to `secrets/token.json`.
7. Optional: to include shared calendars (for example one your EA manages), add their IDs to `CALENDAR_IDS` in `.env`.

When a new Google source is added later, the scheduled run stops with a message asking you to run `--auth` again. It won't try to open a browser at 8am.

### 4. Wispr Flow
There's nothing to set up. Wispr Flow has no public API, so the job reads its database on this PC (`%APPDATA%\Wispr Flow`) in read-only mode. That means the job must run on the PC where Wispr Flow is installed.
- Meetings are processed once when they end, and once more when Wispr's AI summary is ready.
- Notes you write in Flow are included (`WISPR_INCLUDE_NOTES`).
- **Dictations are off by default.** Turning on `WISPR_INCLUDE_DICTATIONS=true` lets Claude see what you dictate into WhatsApp, email and other apps. That catches promises you make in WhatsApp before WhatsApp is connected. But it also sends anything private you've dictated to the Claude API, so decide deliberately.

### 5. WhatsApp
WhatsApp is read and sent through the **claude.ai WhatsApp connector**, which is already linked to your number. It's the only way to read a personal number's chats without unofficial tools, and Meta's Business API can't read them at all. That connector is only reachable from Claude, so the daily job starts a short background Claude Code run. That run:
1. Lists your chats, and fetches messages from those active in the window.
2. Passes them, unchanged, to a small helper that saves them to `data/whatsapp/<number>.json`. Claude doesn't summarise or rewrite them at this step.
3. The main extraction then reads them like any other source.

The morning summary is sent **from your number to your own "message yourself" chat**, so there's no Meta setup. That chat is never read back as a source.

Setup:
- Set `ME_PHONE` in `.env` to your WhatsApp number, for example `9198xxxxxxxx`.
- Keep the Claude Code VS Code extension installed and signed in. The job finds its `claude.exe` automatically, or you can set `CLAUDE_CLI` to a different path.
- **Names:** the connector only gives phone numbers. Claude adds a number to the People sheet when it can tell who it belongs to, for example from an email signature. You can also type numbers into the **Phone** column yourself, comma-separated if someone has several. Unknown numbers show as "+91… (name unknown)".
- **Groups:** messages arrive without the individual sender, so the owner of a commitment from a group may show as "Unassigned".
- **Speed:** syncing takes a few minutes and grows with how many chats were active. Setting `CLAUDE_CLI_MODEL=sonnet` speeds it up.
- To use Meta's Cloud API for sending instead, set `WHATSAPP_SEND_VIA=cloudapi` and fill in the `WHATSAPP_TOKEN…` settings. To stop reading chats, set `WHATSAPP_SYNC=false`.

### 6. Try it, then schedule it
```powershell
.\.venv\Scripts\python -m secondbrain.main --dry-run          # prints what Claude extracted; writes nothing
.\.venv\Scripts\python -m secondbrain.main --hours 72 --no-whatsapp   # first real run, 3-day backfill
powershell -ExecutionPolicy Bypass -File .\register_task.ps1  # daily 08:00 (this PC is on IST)
```
The scheduled task logs to `logs\YYYY-MM.log`. If the PC is off at 08:00, the task runs as soon as it's back on.

## How de-duplication and "Done" work
- Before each Claude call, the open commitments and pending approvals (with their IDs) are sent along. Claude either updates an existing ID, for example to Done or Approved or with a new due date, or creates a new item.
- As a second check, the code fuzzy-matches new items against existing rows by owner and text, and skips near-duplicates.
- Messages that have already been processed are tracked in `data/state.json`, so a re-run won't double count.
- **You can edit the Excel file.** Changes you make to Status, Due or Notes, and any columns you add, are kept. Close Excel before 08:00. If the file is open, the run writes a timestamped copy instead. A `.bak.xlsx` backup of the previous version is kept.

## Adding sources
Add a module in `secondbrain/sources/` with a `fetch(since) -> list[SourceItem]` function and register it in `SOURCES` in `secondbrain/main.py`. Done: Gmail, Google Calendar, Wispr Flow, WhatsApp.

## Secrets
`.env`, `secrets/`, `data/`, `output/` and `logs/` are all git-ignored. Never commit them, because they contain API keys and email content.
