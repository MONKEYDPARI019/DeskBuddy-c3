"""User-facing errors. Each one says what happened and what to do next."""

from __future__ import annotations

# Exit codes (also listed in HANDOFF.md)
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_NO_BOARD = 3
EXIT_PORT_BUSY = 4
EXIT_NETWORK = 5
EXIT_INTEGRITY = 6
EXIT_FLASH = 7
EXIT_NO_REPLY = 8
EXIT_BUILD = 9
EXIT_INTERRUPTED = 130


class DeskBuddyError(Exception):
    """An error with a human message, a fix hint and a process exit code."""

    exit_code = EXIT_ERROR

    def __init__(self, message: str, hint: str = "", exit_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint
        if exit_code is not None:
            self.exit_code = exit_code


class UsageError(DeskBuddyError):
    exit_code = EXIT_USAGE


class NoBoardError(DeskBuddyError):
    exit_code = EXIT_NO_BOARD


class PortBusyError(DeskBuddyError):
    exit_code = EXIT_PORT_BUSY


class NetworkError(DeskBuddyError):
    exit_code = EXIT_NETWORK


class IntegrityError(DeskBuddyError):
    exit_code = EXIT_INTEGRITY


class FlashError(DeskBuddyError):
    exit_code = EXIT_FLASH


class NoReplyError(DeskBuddyError):
    exit_code = EXIT_NO_REPLY


class BuildError(DeskBuddyError):
    exit_code = EXIT_BUILD


def port_busy(port: str) -> PortBusyError:
    return PortBusyError(
        f"{port} is busy",
        "Close the PlatformIO/Arduino serial monitor (or any other program using the port) and try again.",
    )
