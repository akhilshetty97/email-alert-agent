"""LLM classify step: turn a candidate email into a structured decision.

Sends subject + body to a cheap OpenAI model in JSON mode and returns:
  {is_relevant: bool, category: str, summary: str, action_needed: str}

Guiding principle: bias toward flagging. Missing a real assessment is the
failure we're preventing; an extra notification is cheap.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from dotenv import load_dotenv
from openai import OpenAI

from gmail_client import Email

load_dotenv()

MODEL = "gpt-4o-mini"
BODY_CHAR_LIMIT = 4000  # keep token usage/cost bounded

CATEGORIES = [
    "interview",       # scheduling/confirming an interview or phone screen
    "assessment",      # coding challenge / online assessment / take-home
    "offer",           # job offer or offer-related
    "next_steps",      # advancing, requests for info/availability, other action
    "rejection",       # not moving forward
    "application_ack", # "thanks for applying" auto-acknowledgement, no action
    "other",           # not job-application related
]

SYSTEM_PROMPT = (
    "You triage a job seeker's emails during an active job search. "
    "Decide whether an email needs the person's attention because it is an "
    "important next step in a hiring process (an interview, an assessment or "
    "coding challenge, an offer, or a request that needs their action such as "
    "providing availability or completing a task).\n\n"
    "Set is_relevant=true ONLY for emails that require attention or action. "
    "Routine 'thank you for applying' acknowledgements, rejections, marketing, "
    "newsletters, and job-board digests are is_relevant=false.\n"
    "When genuinely unsure whether something requires action, lean toward "
    "is_relevant=true -- a false alarm is far better than a missed assessment.\n\n"
    f"category must be one of: {', '.join(CATEGORIES)}.\n"
    "summary: one short sentence describing the email.\n"
    "action_needed: what the person must do and any deadline, or 'None' if no "
    "action is required.\n\n"
    "Respond ONLY with a JSON object with keys: is_relevant (boolean), "
    "category (string), summary (string), action_needed (string)."
)


@dataclass
class Classification:
    is_relevant: bool
    category: str
    summary: str
    action_needed: str
    error: str | None = None


_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Add it to a .env file "
                "(see README Step 3)."
            )
        _client = OpenAI()
    return _client


def _build_user_content(email: Email) -> str:
    body = email.body[:BODY_CHAR_LIMIT]
    return (
        f"From: {email.sender}\n"
        f"Subject: {email.subject}\n"
        f"Date: {email.date}\n\n"
        f"Body:\n{body}"
    )


def classify(email: Email) -> Classification:
    """Classify a single email. Never raises for LLM/parse issues.

    On any API or parsing failure, returns a Classification with is_relevant=True
    (fail safe -- surface it rather than silently drop) and an `error` set.
    """
    try:
        client = _get_client()
        resp = client.chat.completions.create(
            model=MODEL,
            response_format={"type": "json_object"},
            temperature=0,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _build_user_content(email)},
            ],
        )
        raw = resp.choices[0].message.content or "{}"
        return _parse(raw)
    except Exception as e:  # network, auth, rate limit, bad JSON, etc.
        return Classification(
            is_relevant=True,
            category="other",
            summary="(classification failed; flagged to be safe)",
            action_needed="Review manually",
            error=str(e),
        )


def _parse(raw: str) -> Classification:
    data = json.loads(raw)
    category = str(data.get("category", "other"))
    if category not in CATEGORIES:
        category = "other"
    return Classification(
        is_relevant=bool(data.get("is_relevant", True)),
        category=category,
        summary=str(data.get("summary", "")).strip(),
        action_needed=str(data.get("action_needed", "None")).strip(),
    )
