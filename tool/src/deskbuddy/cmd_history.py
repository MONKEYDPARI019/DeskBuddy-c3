"""Command history for the installer window's command box: Up / Down bring back earlier commands,
like in PowerShell. Kept between runs in ~/.deskbuddy/command_history.txt (see paths.py)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

MAX_COMMANDS = 100

# Commands that carry a secret are sent but never remembered (the history is a plain text file).
SECRET_PREFIXES = ("otapass set",)


def is_secret(command: str) -> bool:
    """'otapass set hunter2' -> True: keep it out of the history file."""
    words = " ".join(command.lower().split())
    return any(words == p or words.startswith(p + " ") for p in SECRET_PREFIXES)


class CommandHistory:
    """Oldest command first. The position len(items) means "the new line being typed"."""

    def __init__(self, path: Optional[Path] = None, limit: int = MAX_COMMANDS) -> None:
        self.path = path
        self.limit = limit
        self.items: list[str] = []
        self._pos = 0
        self._draft = ""
        if path is not None:
            self._load(path)

    def _load(self, path: Path) -> None:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            lines = []  # no history yet, or an unreadable file: start empty
        self.items = [line for line in lines if line.strip()][-self.limit :]
        self._pos = len(self.items)

    def _save(self) -> None:
        if self.path is None:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text("".join(f"{command}\n" for command in self.items), encoding="utf-8")
        except OSError:
            pass  # the history is a convenience: it must never stop a command from being sent

    def add(self, command: str) -> None:
        """Remember a sent command (not twice in a row, never a password) and go back to the new line."""
        command = command.strip()
        if command and not is_secret(command) and (not self.items or self.items[-1] != command):
            self.items.append(command)
            del self.items[: -self.limit]
            self._save()
        self.reset()

    def older(self, current: str) -> Optional[str]:
        """Up arrow: the command before the one shown, or None at the oldest.

        `current` is what's in the box; it comes back when Down goes past the newest command.
        """
        if self._pos == 0:
            return None
        if self._pos == len(self.items):
            self._draft = current
        self._pos -= 1
        return self.items[self._pos]

    def newer(self) -> Optional[str]:
        """Down arrow: the command after the one shown; past the newest, the text that was being typed."""
        if self._pos >= len(self.items):
            return None
        self._pos += 1
        return self.items[self._pos] if self._pos < len(self.items) else self._draft

    def reset(self) -> None:
        """Back to the new line (after sending, or Esc)."""
        self._pos = len(self.items)
        self._draft = ""
