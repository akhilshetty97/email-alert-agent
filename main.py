"""Entrypoint: fetch -> skip processed -> pre-filter -> classify -> notify.

Full pipeline:
  fetch (Gmail) -> remember (Gmail label) -> pre-filter (cheap keyword/ATS check)
  -> classify (LLM, only on candidates) -> notify (Telegram, only if relevant)

Dedup is stateless: processed emails get a Gmail label (PROCESSED_LABEL) and are
excluded from the fetch query, so no local state file or DB is needed. Labeling
is deliberate: an email is labeled once it's been fully handled. If a relevant
email's Telegram send fails, it is NOT labeled, so the next run retries rather
than silently losing the alert.

Runs once and exits. Schedule it with cron or a CI scheduler (see README).

Run:  python main.py
"""

import sys

import classifier
import notifier
import prefilter
from gmail_client import GmailClient

PROCESSED_LABEL = "JobAgentProcessed"
# Only look at unprocessed mail from the last day. Label dedup prevents repeats,
# so a 1-day window safely covers the largest gap between scheduled runs.
FETCH_QUERY = f"-label:{PROCESSED_LABEL} newer_than:1d"
SNIPPET_LEN = 100


def run_once(client: GmailClient, label_id: str) -> None:
    message_ids = client.list_message_ids(FETCH_QUERY)
    print(f"Fetched {len(message_ids)} unprocessed emails from the last day.\n")

    if not message_ids:
        print("Nothing new to process.")
        return

    if not notifier.is_configured():
        print(
            "Note: Telegram not configured (TELEGRAM_BOT_TOKEN / "
            "TELEGRAM_CHAT_ID). Relevant emails will be printed but not sent, "
            "and will be retried next run.\n"
        )

    candidates = 0
    relevant = 0
    notified = 0
    processed = 0
    for msg_id in message_ids:
        email = client.get_message(msg_id)
        passed, reason = prefilter.check(email)

        if not passed:
            snippet = email.snippet[:SNIPPET_LEN].replace("\n", " ")
            print(f"[  skip   ] {email.subject}")
            print(f"            From:   {email.sender}")
            print(f"            Reason: {reason}")
            print(f"            {snippet}")
            print()
            client.add_label(msg_id, label_id)
            processed += 1
            continue

        candidates += 1
        result = classifier.classify(email)
        flag = "RELEVANT" if result.is_relevant else "not rel."
        print(f"[CLASSIFY:{flag}] {email.subject}")
        print(f"            From:     {email.sender}")
        print(f"            Category: {result.category}")
        print(f"            Summary:  {result.summary}")
        print(f"            Action:   {result.action_needed}")
        if result.error:
            print(f"            (error:   {result.error})")

        if not result.is_relevant:
            print()
            client.add_label(msg_id, label_id)
            processed += 1
            continue

        relevant += 1
        sent = notifier.notify(email, result)
        if sent:
            notified += 1
            print("            -> Telegram alert sent")
            client.add_label(msg_id, label_id)
            processed += 1
        else:
            # Don't label: retry the alert on the next run.
            print("            -> alert NOT sent; will retry next run")
        print()

    print(
        f"Processed {len(message_ids)} emails: "
        f"{candidates} passed pre-filter, {relevant} relevant, "
        f"{notified} notified, {len(message_ids) - candidates} filtered out. "
        f"({len(message_ids) - processed} left unlabeled for retry)"
    )


def main() -> None:
    print("Authenticating to Gmail (a browser may open on first run)...")
    try:
        client = GmailClient()
    except FileNotFoundError as e:
        print(f"\nSetup incomplete: {e}", file=sys.stderr)
        sys.exit(1)

    label_id = client.ensure_label(PROCESSED_LABEL)
    run_once(client, label_id)


if __name__ == "__main__":
    main()
