"""SHA-256 helpers and the `SHA256SUMS` file format (`<hex>  <name>` per line, as sha256sum writes)."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from deskbuddy.errors import IntegrityError

_LINE_RE = re.compile(r"^([0-9a-fA-F]{64}) [ *](.+)$")
_CHUNK = 1024 * 1024


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_sha256sums(text: str) -> dict[str, str]:
    """Parse sha256sum output; ignores blank, comment and malformed lines."""
    result: dict[str, str] = {}
    for line in text.splitlines():
        match = _LINE_RE.match(line.strip())
        if match:
            result[match.group(2).strip()] = match.group(1).lower()
    return result


def format_sha256sums(hashes: dict[str, str]) -> str:
    return "".join(f"{hashes[name]}  {name}\n" for name in sorted(hashes))


def verify_sha256(path: Path, expected: str) -> None:
    actual = sha256_file(path)
    if actual != expected.lower():
        raise IntegrityError(
            f"{path.name} failed the checksum test (expected {expected[:12]}..., got {actual[:12]}...)",
            "The download is damaged or was tampered with. Run the command again; "
            "if it keeps failing, report it on GitHub.",
        )
