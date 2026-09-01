"""Pipeline: fetch -> skip processed -> pre-filter -> classify -> notify.

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

import logging
import os
import sys

from . import classifier
from . import notifier
from . import prefilter
from .gmail_client import GmailClient

PROCESSED_LABEL = "JobAgentProcessed"
# Only look at unprocessed mail from the last day. Label dedup prevents repeats,
# so a 1-day window safely covers the largest gap between scheduled runs.
FETCH_QUERY = f"-label:{PROCESSED_LABEL} newer_than:1d"

# One token file per Gmail account
TOKEN_FILES = [
    t.strip() for t in os.getenv("GMAIL_TOKEN_FILES", "token.json").split(",") if t.strip()
]

DEBUG = os.getenv("AGENT_DEBUG") == "1"
logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("agent")


def run_once(client: GmailClient, label_id: str, account: str = "") -> None:
    log.info("Step: fetch unprocessed emails (last 1 day)")
    message_ids = client.list_message_ids(FETCH_QUERY)
    log.info("Fetched %d unprocessed email(s)", len(message_ids))
    if not message_ids:
        log.info("Nothing to process; done")
        return

    if not notifier.is_configured():
        log.warning(
            "Telegram not configured (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID); "
            "relevant emails will not be sent and will retry next run"
        )

    total = len(message_ids)
    candidates = 0
    relevant = 0
    notified = 0
    processed = 0
    log.info("Step: process %d email(s)", total)
    for i, msg_id in enumerate(message_ids, start=1):
        email = client.get_message(msg_id)
        # Sensitive content only in debug (never in public CI logs).
        log.debug("[%d/%d] from=%r subject=%r", i, total, email.sender, email.subject)

        passed, reason = prefilter.check(email)
        if not passed:
            log.info("[%d/%d] pre-filter: skip", i, total)
            client.add_label(msg_id, label_id)
            processed += 1
            continue

        candidates += 1
        result = classifier.classify(email)
        if result.error:
            log.error("[%d/%d] classify failed (flagged safe): %s", i, total, result.error)
        log.info(
            "[%d/%d] pre-filter: pass; classify: %s (%s)",
            i,
            total,
            "relevant" if result.is_relevant else "not-relevant",
            result.category,
        )
        log.debug("[%d/%d] summary=%r action=%r", i, total, result.summary, result.action_needed)

        if not result.is_relevant:
            client.add_label(msg_id, label_id)
            processed += 1
            continue

        relevant += 1
        if notifier.notify(email, result, account=account):
            notified += 1
            log.info("[%d/%d] notify: sent", i, total)
            client.add_label(msg_id, label_id)
            processed += 1
        else:
            # Don't label: retry the alert on the next run.
            log.warning("[%d/%d] notify: failed; left unlabeled for retry", i, total)

    log.info(
        "Done. fetched=%d prefiltered_in=%d relevant=%d notified=%d "
        "filtered_out=%d retry_pending=%d",
        total,
        candidates,
        relevant,
        notified,
        total - candidates,
        total - processed,
    )


def run_account(token_file: str, multi: bool) -> None:
    """Run the pipeline for a single Gmail account (identified by its token file)."""
    log.info("Account: authenticate to Gmail using %r", token_file)
    try:
        client = GmailClient(token_file=token_file)
    except FileNotFoundError as e:
        # Missing token for this account: skip it, but keep other accounts running.
        log.error("Skipping account %r: %s", token_file, e)
        return

    account = client.get_profile_email()
    log.info("Account: authenticated as %s", account)

    log.info("Step: ensure label %r", PROCESSED_LABEL)
    label_id = client.ensure_label(PROCESSED_LABEL)
    # Only tag notifications with the inbox when more than one is configured.
    run_once(client, label_id, account=account if multi else "")


def main() -> None:
    if not TOKEN_FILES:
        log.error("No accounts configured (GMAIL_TOKEN_FILES is empty)")
        sys.exit(1)

    multi = len(TOKEN_FILES) > 1
    log.info("Configured %d account(s)", len(TOKEN_FILES))
    for token_file in TOKEN_FILES:
        run_account(token_file, multi)


if __name__ == "__main__":
    main()
