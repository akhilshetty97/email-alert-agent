"""Gmail client: OAuth handling, message fetching, and label management.

Exposes a small surface:
  - GmailClient.list_recent_messages()
  - GmailClient.get_message(message_id)
  - GmailClient.ensure_label(name)
  - GmailClient.add_label(message_id, label_id)
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# gmail.modify is needed to add our "processed" label (readonly can't modify).
# If you change scopes, delete token.json to re-consent.
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"


@dataclass
class Email:
    id: str
    sender: str
    subject: str
    date: str
    body: str
    snippet: str
    rfc822_msgid: str = ""  # RFC822 Message-ID header, used for Gmail deep links


def _get_header(headers: list[dict], name: str) -> str:
    """Case-insensitive lookup of a header value, empty string if missing."""
    name = name.lower()
    for h in headers:
        if h.get("name", "").lower() == name:
            return h.get("value", "")
    return ""


def _decode_body_part(data: str) -> str:
    """Decode a base64url-encoded body part to text."""
    if not data:
        return ""
    decoded = base64.urlsafe_b64decode(data.encode("utf-8"))
    return decoded.decode("utf-8", errors="replace")


def _extract_plain_text(payload: dict) -> str:
    """Walk the MIME tree and return the best-effort plaintext body.

    Prefers text/plain; falls back to text/html (tags left intact) if that's
    all that's available.
    """
    mime_type = payload.get("mimeType", "")
    body_data = payload.get("body", {}).get("data", "")

    if mime_type == "text/plain" and body_data:
        return _decode_body_part(body_data)

    parts = payload.get("parts")
    if parts:
        # First pass: look for text/plain anywhere in the tree.
        for part in parts:
            text = _extract_plain_text(part)
            if part.get("mimeType") == "text/plain" and text:
                return text
        # Second pass: accept whatever text we can find (e.g. text/html).
        for part in parts:
            text = _extract_plain_text(part)
            if text:
                return text

    if mime_type == "text/html" and body_data:
        return _decode_body_part(body_data)

    return ""


class GmailClient:
    def __init__(self, credentials_file: str = CREDENTIALS_FILE, token_file: str = TOKEN_FILE):
        self.credentials_file = credentials_file
        self.token_file = token_file
        self.service = self._build_service()

    def _load_credentials(self) -> Credentials:
        creds: Credentials | None = None
        if os.path.exists(self.token_file):
            creds = Credentials.from_authorized_user_file(self.token_file, SCOPES)

        # A stored token granted for different scopes can't be reused or
        # refreshed for the new scopes; force a fresh consent in that case.
        if creds and not creds.has_scopes(SCOPES):
            creds = None

        if creds and creds.valid:
            return creds

        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError:
                creds = None  # expired/revoked/scope-changed -> re-consent below

        if creds is None or not creds.valid:
            if not os.path.exists(self.credentials_file):
                raise FileNotFoundError(
                    f"Missing {self.credentials_file}. See README Step 1 for how to "
                    "create OAuth Desktop credentials and download this file."
                )
            flow = InstalledAppFlow.from_client_secrets_file(self.credentials_file, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(self.token_file, "w") as f:
            f.write(creds.to_json())
        return creds

    def _build_service(self):
        creds = self._load_credentials()
        return build("gmail", "v1", credentials=creds)

    def get_profile_email(self) -> str:
        """Return the authenticated account's email address."""
        profile = self.service.users().getProfile(userId="me").execute()
        return profile.get("emailAddress", "")

    def list_recent_messages(self, max_results: int = 20, query: str = "") -> list[str]:
        """Return recent message IDs (newest first).

        `query` accepts Gmail search syntax (e.g. "newer_than:7d").
        """
        resp = (
            self.service.users()
            .messages()
            .list(userId="me", maxResults=max_results, q=query)
            .execute()
        )
        return [m["id"] for m in resp.get("messages", [])]

    def list_message_ids(self, query: str) -> list[str]:
        """Return all message IDs matching a Gmail search query (paginated)."""
        ids = []
        page_token = None
        while True:
            resp = (
                self.service.users()
                .messages()
                .list(userId="me", q=query, pageToken=page_token)
                .execute()
            )
            ids.extend(m["id"] for m in resp.get("messages", []))
            page_token = resp.get("nextPageToken")
            if not page_token:
                return ids

    def get_message(self, message_id: str) -> Email:
        msg = (
            self.service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )
        payload = msg.get("payload", {})
        headers = payload.get("headers", [])
        return Email(
            id=message_id,
            sender=_get_header(headers, "From"),
            subject=_get_header(headers, "Subject"),
            date=_get_header(headers, "Date"),
            body=_extract_plain_text(payload),
            snippet=msg.get("snippet", ""),
            rfc822_msgid=_get_header(headers, "Message-ID").strip("<>"),
        )

    def ensure_label(self, name: str) -> str:
        """Return the label id for `name`, creating the label if it's missing."""
        resp = self.service.users().labels().list(userId="me").execute()
        for label in resp.get("labels", []):
            if label.get("name") == name:
                return label["id"]
        created = (
            self.service.users()
            .labels()
            .create(
                userId="me",
                body={
                    "name": name,
                    "labelListVisibility": "labelShow",
                    "messageListVisibility": "show",
                },
            )
            .execute()
        )
        return created["id"]

    def add_label(self, message_id: str, label_id: str) -> None:
        """Add a label to a message. Only touches the given label; read/unread
        status (the UNREAD label) is left untouched."""
        self.service.users().messages().modify(
            userId="me", id=message_id, body={"addLabelIds": [label_id]}
        ).execute()
