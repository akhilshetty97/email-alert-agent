"""Telegram notification step.

Sends a formatted alert for a relevant email via the Telegram Bot API.
Config comes from .env: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID.

Run this module directly to discover your chat id after messaging your bot:
    python -m linkedin_park.notifier
"""

from __future__ import annotations

import html
import os
from email.utils import parseaddr
from urllib.parse import quote

import requests
from dotenv import load_dotenv

from .classifier import Classification
from .gmail_client import Email

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
API_BASE = "https://api.telegram.org"
TIMEOUT = 15


def is_configured() -> bool:
    return bool(BOT_TOKEN and CHAT_ID)


# Human-friendly labels for the classifier's category codes.
CATEGORY_LABELS = {
    "interview": "Interview",
    "assessment": "Assessment / coding test",
    "offer": "Offer",
    "next_steps": "Next step",
    "rejection": "Rejection",
    "application_ack": "Application received",
    "other": "Worth a look",
}


def _sender_name(sender: str) -> str:
    """Extract a display name from a From header, falling back to the address."""
    name, addr = parseaddr(sender)
    return name or addr or sender


def _gmail_link(email: Email) -> str:
    """Gmail link to the specific message via an rfc822msgid search.

    Uses a query-based search URL (?q=) rather than only a #fragment: query
    strings survive mobile browser handoff better, so this behaves better on
    phones. Also keeps the #search fragment for the desktop web app.

    Note: this can only ever open in a *browser*. The Gmail mobile app does not
    register mail.google.com for deep links, so no URL can open a specific
    message in the native app. Returns "" if we have no Message-ID.
    """
    msgid = email.rfc822_msgid.strip("<>")
    if not msgid:
        return ""
    query = f"rfc822msgid:{msgid}"
    q_enc = quote(query, safe="")
    return (
        "https://mail.google.com/mail/u/0/"
        f"?view=tl&search=all&q={q_enc}#search/{q_enc}"
    )


def format_message(email: Email, c: Classification) -> str:
    """Build a compact HTML Telegram message. All dynamic text is escaped."""
    label = CATEGORY_LABELS.get(c.category, c.category.replace("_", " ").title())
    category = html.escape(label)
    sender = html.escape(_sender_name(email.sender))

    lines = [f"<b>{category}</b> - {sender}"]
    if c.summary:
        lines.append(f"<b>Summary:</b> {html.escape(c.summary)}")

    action = c.action_needed.strip()
    if action and action.lower() != "none":
        lines.append(f"<b>Likely action:</b> {html.escape(action)}")

    link = _gmail_link(email)
    if link:
        lines.append(f'<a href="{html.escape(link)}">Open in Gmail</a>')

    return "\n\n".join(lines)


def send(text: str) -> bool:
    """Send a message. Returns True on success, False otherwise (never raises)."""
    if not is_configured():
        print(
            "Telegram not configured (set TELEGRAM_BOT_TOKEN and "
            "TELEGRAM_CHAT_ID in .env). Skipping send."
        )
        return False
    try:
        resp = requests.post(
            f"{API_BASE}/bot{BOT_TOKEN}/sendMessage",
            json={
                "chat_id": CHAT_ID,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=TIMEOUT,
        )
        if resp.status_code != 200:
            print(f"Telegram send failed ({resp.status_code}): {resp.text}")
            return False
        return True
    except requests.RequestException as e:
        print(f"Telegram send error: {e}")
        return False


def notify(email: Email, c: Classification) -> bool:
    return send(format_message(email, c))


def _print_chat_ids() -> None:
    """Helper: call getUpdates and print chat ids from recent messages.

    Message your bot in Telegram first, then run `python -m linkedin_park.notifier`.
    """
    if not BOT_TOKEN:
        print("Set TELEGRAM_BOT_TOKEN in .env first.")
        return
    resp = requests.get(f"{API_BASE}/bot{BOT_TOKEN}/getUpdates", timeout=TIMEOUT)
    data = resp.json()

    if not data.get("ok"):
        print(
            "Telegram API returned an error (your token is likely wrong):\n"
            f"  {data}\n"
            "Copy the token exactly from BotFather (the string after "
            "'Use this token to access the HTTP API:')."
        )
        return

    updates = data.get("result", [])
    if not updates:
        print(
            "Token works, but no messages yet. In Telegram, open a chat with "
            "your bot (search its @username), press START, send any message, "
            "then run this again.\n"
            "Note: getUpdates only shows recent messages, and none if a webhook "
            "is set."
        )
        return
    seen = {}
    for u in updates:
        msg = u.get("message") or u.get("edited_message") or {}
        chat = msg.get("chat", {})
        if chat.get("id") is not None:
            seen[chat["id"]] = chat.get("username") or chat.get("first_name", "")
    print("Chat id(s) that have messaged your bot:")
    for cid, name in seen.items():
        print(f"  {cid}  ({name})")
    print("\nAdd the correct one to .env as TELEGRAM_CHAT_ID=<id>")


if __name__ == "__main__":
    _print_chat_ids()
