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

## Roadmap

- [x] Step 1 — Gmail auth + fetch
- [ ] Step 2 — Pre-filter + remember (dedup seen message IDs)
- [ ] Step 3 — Classify with OpenAI (structured JSON)
- [ ] Step 4 — Notify via Telegram
- [ ] Step 5 — Schedule (poll loop / cron)
