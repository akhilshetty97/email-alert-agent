# Gmail Job-Alert Agent

A personal, single-user tool that scans Gmail, flags important job emails
(interviews, assessments, next steps), and pings you on Telegram.

Stack: Python + Telegram + OpenAI.

Pipeline: `fetch -> skip already-processed -> pre-filter -> classify (LLM) -> notify`.
Dedup is stateless — processed emails get a Gmail label (`JobAgentProcessed`) and
are excluded from the next fetch, so there's no state file or DB to manage.

---

## Step 1: One-time Google Cloud setup

You only do this once. Budget ~15 minutes.

1. Go to https://console.cloud.google.com and create a new project
   (top bar project dropdown -> "New Project"). Name it anything, e.g.
   `gmail-job-agent`.

2. Enable the Gmail API:
   - APIs & Services -> Library -> search "Gmail API" -> **Enable**.

3. Configure the OAuth consent screen:
   - APIs & Services -> OAuth consent screen.
   - User type: **External** -> Create.
   - Fill in the required fields (app name, your email for support + developer
     contact). You can leave everything else blank.
   - **Leave the app in "Testing" mode** (do NOT publish). This avoids Google's
     app-verification process.
   - On the "Test users" step, add **your own Gmail address** as a test user.
     Only test users can authorize the app while it's in Testing mode.

4. Create OAuth credentials:
   - APIs & Services -> Credentials -> Create Credentials -> **OAuth client ID**.
   - Application type: **Desktop app**. Name it anything.
   - Click Create, then **Download JSON**.

5. Save that file as `credentials.json` in this project's root directory
   (same folder as `main.py`). It is git-ignored and never committed.

> Note: while the app is in Testing mode, the refresh token can expire after
> ~7 days, so you may occasionally need to re-run the OAuth flow. That's fine
> for local use. For unattended automation, publish the app (see "Automating"
> below) so the token stops expiring.

---

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
python main.py
```

The first run opens a browser window for Google sign-in. Approve the
`gmail.modify` scope (needed to add the `JobAgentProcessed` label; you'll see an
"unverified app" warning — expected in Testing mode, click through with your
test-user account). A `token.json` is written so future runs don't prompt again.

Each run fetches unprocessed emails from the last day, pre-filters, classifies
the survivors, sends Telegram alerts for the relevant ones, and labels everything
it handled so it won't be reprocessed.

---

## Step 3: OpenAI key

Create a file named `.env` in the project root (git-ignored):

```
OPENAI_API_KEY=sk-...your key...
```

Get a key at https://platform.openai.com/api-keys. Step 3 uses `gpt-4o-mini`
(cheap). Only emails that pass the pre-filter are sent to the model, so cost
stays near zero.

If `OPENAI_API_KEY` is missing or a call fails, the classifier fails *safe*:
it marks the email relevant and records the error, so nothing important is
silently dropped.

## Step 4: Telegram setup

1. In Telegram, message **@BotFather**, send `/newbot`, follow the prompts, and
   copy the **bot token** it gives you.
2. Open a chat with your new bot and send it any message (e.g. "hi"). This is
   required so the bot can see your chat id.
3. Add the token to `.env`:

   ```
   TELEGRAM_BOT_TOKEN=123456:ABC-your-token
   ```

4. Discover your chat id:

   ```bash
   python notifier.py
   ```

   It prints the chat id(s) that have messaged your bot. Add it to `.env`:

   ```
   TELEGRAM_CHAT_ID=<your id>
   ```

Now relevant emails trigger a Telegram alert. If Telegram isn't configured, the
pipeline still runs and prints results; relevant emails are left unmarked so
they retry once you configure it.

## How dedup works

Processed emails get the Gmail label `JobAgentProcessed`, and the fetch query is
`-label:JobAgentProcessed newer_than:1d`, so they're never reprocessed. Adding the
label only touches that label — it does not mark the email read.

If a relevant email's Telegram send fails, it is deliberately left unlabeled so
the next run retries it (no silently lost alerts). To reprocess everything, just
remove the `JobAgentProcessed` label from those emails in Gmail.

## Automating (GitHub Actions cron)

Runs the agent on a schedule for free, with no server. State lives in Gmail
(the label), so nothing needs to persist between runs.

1. **Publish the OAuth app** so the refresh token stops expiring after ~7 days:
   Google Cloud Console -> APIs & Services -> OAuth consent screen ->
   **Publishing status -> Publish app**. For personal restricted-scope use this
   is fine; the "unverified" warning stays but the token becomes long-lived.
   Then re-run `python main.py` locally once to mint a fresh `token.json`.

2. **Add repo secrets** (Settings -> Secrets and variables -> Actions). The two
   Google files are base64-encoded so they survive as single-line secrets:

   ```bash
   base64 -i credentials.json | pbcopy   # paste into GOOGLE_CREDENTIALS_B64
   base64 -i token.json       | pbcopy   # paste into GOOGLE_TOKEN_B64
   ```

   Secrets to create:
   - `GOOGLE_CREDENTIALS_B64`
   - `GOOGLE_TOKEN_B64`
   - `OPENAI_API_KEY`
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`

3. The workflow at [.github/workflows/agent.yml](.github/workflows/agent.yml)
   runs 4x/day (11am, 3pm, 7pm, 11pm Pacific) and can be triggered manually from
   the Actions tab (`workflow_dispatch`). Cron times are in **UTC** and do not
   observe DST — adjust `0 2,6,18,22 * * *` if your offset changes.

Notes:
- Cost: ~4 runs/day is far within the free Actions minutes.
- GitHub disables scheduled workflows after 60 days of repo inactivity; a manual
  run or any commit re-arms them.
- If you re-consent locally and `token.json` changes, update `GOOGLE_TOKEN_B64`.

## Roadmap

- [x] Step 1 — Gmail auth + fetch
- [x] Step 2 — Pre-filter + remember (Gmail-label dedup)
- [x] Step 3 — Classify with OpenAI (structured JSON)
- [x] Step 4 — Notify via Telegram
- [x] Step 5 — Schedule (GitHub Actions cron)
