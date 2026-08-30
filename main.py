"""Step 4 entrypoint: fetch -> skip seen -> pre-filter -> classify -> notify.

Full pipeline:
  fetch (Gmail) -> remember (skip seen) -> pre-filter (cheap keyword/ATS check)
  -> classify (LLM, only on candidates) -> notify (Telegram, only if relevant)

Seen-marking is deliberate: an email is marked seen once it's been fully
handled. If a relevant email's Telegram send fails, it is NOT marked seen, so
the next run retries rather than silently losing the alert.

Run:  python main.py
"""

import sys

import classifier
import notifier
import prefilter
from gmail_client import GmailClient
from store import SeenStore

MAX_EMAILS = 20
SNIPPET_LEN = 100


def main() -> None:
    print("Authenticating to Gmail (a browser may open on first run)...")
    try:
        client = GmailClient()
    except FileNotFoundError as e:
        print(f"\nSetup incomplete: {e}", file=sys.stderr)
        sys.exit(1)

    seen = SeenStore()
    message_ids = client.list_recent_messages(max_results=MAX_EMAILS)
    if not message_ids:
        print("No messages found.")
        return

    new_ids = [mid for mid in message_ids if not seen.is_seen(mid)]
    skipped = len(message_ids) - len(new_ids)
    print(
        f"\nFetched {len(message_ids)} recent emails "
        f"({skipped} already seen, {len(new_ids)} new).\n"
    )

    if not new_ids:
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
    to_mark_seen = []
    for msg_id in new_ids:
        email = client.get_message(msg_id)
        passed, reason = prefilter.check(email)

        if not passed:
            snippet = email.snippet[:SNIPPET_LEN].replace("\n", " ")
            print(f"[  skip   ] {email.subject}")
            print(f"            From:   {email.sender}")
            print(f"            Reason: {reason}")
            print(f"            {snippet}")
            print()
            to_mark_seen.append(msg_id)
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
            to_mark_seen.append(msg_id)
            continue

        relevant += 1
        sent = notifier.notify(email, result)
        if sent:
            notified += 1
            print("            -> Telegram alert sent")
            to_mark_seen.append(msg_id)
        else:
            # Don't mark seen: retry the alert on the next run.
            print("            -> alert NOT sent; will retry next run")
        print()

    # Mark only fully-handled emails as seen.
    seen.mark_many_seen(to_mark_seen)

    print(
        f"Processed {len(new_ids)} new emails: "
        f"{candidates} passed pre-filter, {relevant} relevant, "
        f"{notified} notified, {len(new_ids) - candidates} filtered out. "
        f"(seen.json now holds {len(seen)} IDs; "
        f"{len(new_ids) - len(to_mark_seen)} pending retry)"
    )


if __name__ == "__main__":
    main()
