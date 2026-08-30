# Gmail Job-Alert Agent

A personal, single-user tool that polls Gmail, flags important job emails
(interviews, assessments, next steps), and (later) pings you on Telegram.

Stack: Python + Telegram + OpenAI. Built in small steps.

**Status: Step 1 — Gmail auth + fetch.**

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
> for a personal tool.

---

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Run (Step 1)

```bash
python main.py
```

The first run opens a browser window for Google sign-in. Approve the
`gmail.readonly` scope (you'll see an "unverified app" warning — that's expected
since the app is in Testing mode; click through with your test-user account).
A `token.json` is written so future runs don't prompt again.

You should see your ~20 most recent emails printed as `sender | subject | snippet`.

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

## Step 2 behavior

`python main.py` now:
1. Fetches recent emails.
2. Skips any whose ID is already in `seen.json` (so nothing is reprocessed).
3. Runs a cheap pre-filter (`prefilter.py`) — job keywords + known ATS senders.
   Deliberately inclusive: borderline emails pass through to avoid missing a
   real assessment. Each email is printed as `CANDIDATE` or `skip` with a reason.
4. Marks everything processed as seen.

Run it twice: the second run should report the first batch as "already seen".
To reprocess from scratch, delete `seen.json`.

## Roadmap

- [x] Step 1 — Gmail auth + fetch
- [x] Step 2 — Pre-filter + remember (dedup seen message IDs)
- [x] Step 3 — Classify with OpenAI (structured JSON)
- [ ] Step 4 — Notify via Telegram
- [ ] Step 5 — Schedule (poll loop / cron)
