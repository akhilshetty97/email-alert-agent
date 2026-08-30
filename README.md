# LinkedIn Park

*An AI agent that catches the job emails you can't afford to miss.*

When you're job hunting, your inbox floods with "thanks for applying"
auto-replies — and the one email that actually matters (an interview invite, a
coding assessment with a deadline) gets buried. **LinkedIn Park** scans your
Gmail, uses an LLM to figure out which emails need your attention, and pings you
on Telegram with a short summary and the action required.

Built after missing a real assessment deadline. Never again.

---

## What it does

- Reads recent Gmail messages via the official Gmail API (OAuth).
- Cheaply pre-filters obvious noise before spending any LLM tokens.
- Classifies the survivors with an LLM into `interview` / `assessment` / `offer` /
  `next_steps` / `rejection` / `application_ack` / `other`.
- Sends a clean Telegram alert (summary + likely action + a link to the email)
  only for the ones that matter.
- Remembers what it has handled using a Gmail label, so you're never pinged twice.

### Pipeline

```
fetch (Gmail) -> pre-filter (keywords/ATS) -> classify (LLM) -> notify (Telegram)
                          \-> label as processed (dedup)
```

Dedup is **stateless**: handled emails get a Gmail label (`JobAgentProcessed`) and
are excluded from the next fetch — no database or state file to manage.

### Tech stack

Python · Gmail API · OpenAI (`gpt-4o-mini`) · Telegram Bot API · GitHub Actions

---

## Prerequisites

- Python 3.11+
- A Google account (Gmail)
- An OpenAI API key
- A Telegram account

---

## Setup

### 1. Google Cloud (Gmail access)

You only do this once (~15 minutes).

1. Create a project at the [Google Cloud Console](https://console.cloud.google.com)
   (top bar -> "New Project").
2. **Enable the Gmail API**: APIs & Services -> Library -> search "Gmail API" -> **Enable**.
3. **Configure the OAuth consent screen**: APIs & Services -> OAuth consent screen.
   - User type: **External**.
   - Fill in app name, your support email, and developer contact. Leave the rest blank.
   - Add **your own Gmail address** as a **Test user**.
4. **Create credentials**: APIs & Services -> Credentials -> Create Credentials ->
   **OAuth client ID** -> Application type **Desktop app** -> Create -> **Download JSON**.
5. Save the file as **`credentials.json`** in the project root. It is git-ignored
   and never committed.

The app uses the `gmail.modify` scope — it reads your mail and adds the
`JobAgentProcessed` label. It never marks mail read, sends, or deletes anything.

### 2. Install

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure keys

Create a `.env` file in the project root (git-ignored):

```
OPENAI_API_KEY=sk-...
TELEGRAM_BOT_TOKEN=123456:ABC-your-token
TELEGRAM_CHAT_ID=123456789
```

- **OpenAI key:** [platform.openai.com/api-keys](https://platform.openai.com/api-keys).
  Only pre-filtered emails hit the model, so cost stays near zero.
- **Telegram bot token:** message [@BotFather](https://t.me/BotFather), send
  `/newbot`, follow the prompts, copy the token.
- **Telegram chat id:** open a chat with your new bot and send it any message,
  then run `python -m linkedin_park.notifier` — it prints the chat id(s) that have messaged
  your bot. Paste the number into `.env`.

### 4. Run

```bash
python main.py
```

The first run opens a browser for Google sign-in. You'll see an "unverified app"
warning (expected) — click **Advanced -> Go to <app> (unsafe)** with your
test-user account and approve. A `token.json` is saved so future runs don't prompt.

Each run fetches unprocessed emails from the last day, classifies them, sends
Telegram alerts for the relevant ones, and labels everything it handled.

---

## Automating (GitHub Actions, free)

Run it on a schedule with no server. State lives in Gmail (the label), so nothing
needs to persist between runs.

1. **Publish the OAuth app** so the refresh token stops expiring after ~7 days:
   Google Cloud Console -> OAuth consent screen -> **Publishing status ->
   Publish app**. (For personal, restricted-scope use this is fine; the
   "unverified" warning stays but the token becomes long-lived.) Publishing
   requires an app name, support email, homepage URL, and privacy policy URL —
   your repo URL and [PRIVACY.md](PRIVACY.md) work for the last two. Then re-run
   `python main.py` once to mint a fresh long-lived `token.json`.

2. **Add repo secrets** (Settings -> Secrets and variables -> Actions). The two
   Google JSON files are base64-encoded so they fit as single-line secrets:

   ```bash
   base64 -i credentials.json | pbcopy   # -> GOOGLE_CREDENTIALS_B64
   base64 -i token.json       | pbcopy   # -> GOOGLE_TOKEN_B64
   ```

   Create these secrets:
   - `GOOGLE_CREDENTIALS_B64`
   - `GOOGLE_TOKEN_B64`
   - `OPENAI_API_KEY`
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`

3. The workflow at [.github/workflows/agent.yml](.github/workflows/agent.yml) runs
   4x/day and supports manual runs from the Actions tab (`workflow_dispatch`).
   Cron times are **UTC** and don't observe DST — the default
   `0 2,6,18,22 * * *` is 11am/3pm/7pm/11pm Pacific; adjust for your timezone.

Notes:
- Cost: 4 runs/day is far within the free Actions minutes.
- GitHub disables scheduled workflows after 60 days of repo inactivity; a manual
  run or any commit re-arms them.
- If you re-consent locally and `token.json` changes, update `GOOGLE_TOKEN_B64`.

---

## Logging

Logs are intentionally high-level, so they're safe even in a public repo (where
Actions logs are world-readable). By default you get step markers, per-email
outcomes, and counts — **no email content**:

```
Step: fetch unprocessed emails (last 1 day)
Fetched 2 unprocessed email(s)
[1/2] pre-filter: pass; classify: relevant (assessment)
[1/2] notify: sent
Done. fetched=2 prefiltered_in=2 relevant=2 notified=2 filtered_out=0 retry_pending=0
```

For local debugging, set `AGENT_DEBUG=1` to also log subjects, senders, and
summaries. Never set this in CI:

```bash
AGENT_DEBUG=1 python main.py
```

---

## How dedup works

Handled emails get the Gmail label `JobAgentProcessed`; the fetch query is
`-label:JobAgentProcessed newer_than:1d`, so they're never reprocessed. Adding the
label only touches that label — it does not mark the email read. If a relevant
email's Telegram send fails, it's deliberately left unlabeled so the next run
retries it (no silently lost alerts). To reprocess an email, remove the label
from it in Gmail.

---

## Security

- Secrets (`credentials.json`, `token.json`, `.env`) are git-ignored — never commit them.
- In CI they're stored as encrypted GitHub Actions secrets; fork pull requests
  cannot access them, and the workflow's `GITHUB_TOKEN` is limited to `contents: read`.
- Revoke the app's access anytime at
  [myaccount.google.com/permissions](https://myaccount.google.com/permissions).
- Enable 2FA on your Google and GitHub accounts.

---

## Project layout

| File | Role |
|------|------|
| `main.py` | Thin entrypoint (`from linkedin_park import main`) |
| `linkedin_park/pipeline.py` | Orchestrates the pipeline |
| `linkedin_park/gmail_client.py` | Gmail OAuth, fetching, labels |
| `linkedin_park/prefilter.py` | Cheap keyword/ATS pre-filter |
| `linkedin_park/classifier.py` | LLM classification (structured JSON) |
| `linkedin_park/notifier.py` | Telegram formatting + sending |
| `.github/workflows/agent.yml` | Scheduled runner |
