"""Persistent "remember" store: which Gmail message IDs we've already processed.

Backed by a plain JSON file (seen.json). Simple and inspectable; fine for a
single-user tool. Prevents re-notifying the same email on every poll.
"""

from __future__ import annotations

import json
import os

SEEN_FILE = "seen.json"


class SeenStore:
    def __init__(self, path: str = SEEN_FILE):
        self.path = path
        self._ids: set[str] = self._load()

    def _load(self) -> set[str]:
        if not os.path.exists(self.path):
            return set()
        try:
            with open(self.path) as f:
                data = json.load(f)
            return set(data.get("seen_ids", []))
        except (json.JSONDecodeError, OSError):
            # Corrupt or unreadable store: start fresh rather than crashing.
            return set()

    def is_seen(self, message_id: str) -> bool:
        return message_id in self._ids

    def mark_seen(self, message_id: str) -> None:
        self._ids.add(message_id)
        self._save()

    def mark_many_seen(self, message_ids: list[str]) -> None:
        self._ids.update(message_ids)
        self._save()

    def _save(self) -> None:
        with open(self.path, "w") as f:
            json.dump({"seen_ids": sorted(self._ids)}, f, indent=2)

    def __len__(self) -> int:
        return len(self._ids)
