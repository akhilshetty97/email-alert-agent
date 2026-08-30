"""Step 3 entrypoint: fetch -> skip seen -> pre-filter -> classify -> report.

Pipeline so far:
  fetch (Gmail) -> remember (skip seen) -> pre-filter (cheap keyword/ATS check)
  -> classify (LLM, only on candidates)

Notify comes next. For now we print the structured classification for each
candidate, then mark everything we processed as seen so the next run skips it.

Run:  python main.py
"""

import sys

import classifier
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

    candidates = 0
    relevant = 0
    processed_ids = []
    for msg_id in new_ids:
        email = client.get_message(msg_id)
        passed, reason = prefilter.check(email)
        processed_ids.append(msg_id)

        if not passed:
            snippet = email.snippet[:SNIPPET_LEN].replace("\n", " ")
            print(f"[  skip   ] {email.subject}")
            print(f"            From:   {email.sender}")
            print(f"            Reason: {reason}")
            print(f"            {snippet}")
            print()
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
        print()
        if result.is_relevant:
            relevant += 1

    # Mark everything we processed as seen so we don't reprocess next run.
    seen.mark_many_seen(processed_ids)

    print(
        f"Processed {len(processed_ids)} new emails: "
        f"{candidates} passed pre-filter, {relevant} classified relevant, "
        f"{len(processed_ids) - candidates} filtered out. "
        f"(seen.json now holds {len(seen)} IDs)"
    )


if __name__ == "__main__":
    main()
