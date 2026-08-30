"""Step 1 entrypoint: authenticate to Gmail and print recent emails.

Run:  python main.py
First run opens a browser for OAuth; subsequent runs reuse token.json.
"""

import sys

from gmail_client import GmailClient

MAX_EMAILS = 20
SNIPPET_LEN = 100


def main() -> None:
    print("Authenticating to Gmail (a browser may open on first run)...")
    try:
        client = GmailClient()
    except FileNotFoundError as e:
        print(f"\nSetup incomplete: {e}", file=sys.stderr)
        sys.exit(1)

    message_ids = client.list_recent_messages(max_results=MAX_EMAILS)
    if not message_ids:
        print("No messages found.")
        return

    print(f"\nFetched {len(message_ids)} recent emails:\n")
    for i, msg_id in enumerate(message_ids, start=1):
        email = client.get_message(msg_id)
        snippet = email.snippet[:SNIPPET_LEN].replace("\n", " ")
        print(f"{i:2d}. From:    {email.sender}")
        print(f"    Subject: {email.subject}")
        print(f"    Snippet: {snippet}")
        print()


if __name__ == "__main__":
    main()
