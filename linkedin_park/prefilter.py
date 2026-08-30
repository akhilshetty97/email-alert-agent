"""Cheap pre-filter: decide if an email is worth an LLM call.

Design principle: optimize against FALSE NEGATIVES. This runs before any paid
LLM call, so it's fine to let borderline emails through (the classifier sorts
them out later). What we must NOT do is silently drop a real assessment.

A pass here just means "plausibly job-related" -> send to the classifier.
"""

from __future__ import annotations

from .gmail_client import Email

# Substrings checked (case-insensitive) against subject + body.
KEYWORDS = [
    # interview / scheduling
    "interview",
    "next step",
    "next steps",
    "schedule",
    "availability",
    "available times",
    "calendar",
    "call with",
    "phone screen",
    "recruiter screen",
    "hiring team",
    "hiring manager",
    # assessments / take-homes
    "assessment",
    "coding challenge",
    "coding test",
    "take-home",
    "take home",
    "technical challenge",
    "online assessment",
    "complete the",
    "hackerrank",
    "codesignal",
    "codility",
    "leetcode",
    # offers / outcomes
    "offer",
    "moving forward",
    "move forward",
    "next round",
    "final round",
    "onsite",
    "on-site",
    # generic application signals
    "your application",
    "application status",
    "position",
    "opportunity",
]

# Sender substrings for common Applicant Tracking Systems (ATS) and job boards.
# Matched against the raw From header (name + address).
ATS_SENDERS = [
    "greenhouse.io",
    "greenhouse-mail.io",
    "lever.co",
    "hire.lever.co",
    "ashbyhq.com",
    "workday",
    "myworkday.com",
    "icims.com",
    "smartrecruiters.com",
    "jobvite.com",
    "taleo.net",
    "successfactors",
    "bamboohr.com",
    "workable.com",
    "breezy.hr",
    "recruitee.com",
    "linkedin.com",
    "indeed.com",
    "ziprecruiter.com",
]


def check(email: Email) -> tuple[bool, str]:
    """Return (passed, reason).

    `passed` True means the email should go on to the classifier.
    `reason` is a short human-readable explanation for logging/debugging.
    """
    haystack = f"{email.subject}\n{email.body}".lower()
    sender = email.sender.lower()

    matched_keywords = [kw for kw in KEYWORDS if kw in haystack]
    matched_ats = [s for s in ATS_SENDERS if s in sender]

    if matched_keywords or matched_ats:
        bits = []
        if matched_keywords:
            bits.append("keywords=" + ",".join(matched_keywords[:5]))
        if matched_ats:
            bits.append("ats=" + ",".join(matched_ats))
        return True, "; ".join(bits)

    return False, "no job-related signals"
