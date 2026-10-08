"""GitHub Releases: list releases, pick and download firmware (sha256-verified), fetch the source archive.

Only the standard library is used (urllib). A GITHUB_TOKEN environment variable, if set, is sent
to api.github.com only (never to download hosts, never on redirects) to lift the API rate limit.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import tempfile
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Optional
from urllib.parse import urlparse

from deskbuddy import REPO, __version__
from deskbuddy.checksums import parse_sha256sums, sha256_file, verify_sha256
from deskbuddy.envs import parse_image_filename, to_friendly
from deskbuddy.errors import IntegrityError, NetworkError, UsageError
from deskbuddy.versions import to_tag, version_key

API_ROOT = "https://api.github.com"
API_HOST = "api.github.com"
SUMS_NAME = "SHA256SUMS"
MAX_DOWNLOAD_BYTES = 200 * 1024 * 1024
MAX_TEXT_BYTES = 1024 * 1024
MAX_EXTRACT_BYTES = 500 * 1024 * 1024
_CHUNK = 64 * 1024
_TAG_RE = re.compile(r"^v[0-9A-Za-z.\-+]{1,40}$")

Progress = Callable[[float], None]


@dataclass(frozen=True)
class Asset:
    name: str
    url: str
    size: int
    sha256: Optional[str]


@dataclass(frozen=True)
class Release:
    tag: str
    name: str
    published_at: str
    prerelease: bool
    assets: tuple[Asset, ...]
    zipball_url: str

    @property
    def date(self) -> str:
        return self.published_at[:10]

    def asset(self, name: str) -> Optional[Asset]:
        return next((a for a in self.assets if a.name == name), None)

    def image_for(self, pio_env: str) -> Asset:
        for asset in self.assets:
            parsed = parse_image_filename(asset.name)
            if parsed and parsed[0] == pio_env:
                return asset
        raise UsageError(
            f"Release {self.tag} has no {to_friendly(pio_env)} firmware",
            "Run 'deskbuddy versions' to see what each release contains.",
        )


def _unexpected(detail: str) -> NetworkError:
    return NetworkError(f"GitHub sent an unexpected answer ({detail})", "Try again in a minute.")


def parse_release(data: Any) -> Release:
    try:
        tag = str(data["tag_name"])
        assets = tuple(
            Asset(
                name=str(a["name"]),
                url=str(a["browser_download_url"]),
                size=int(a.get("size") or 0),
                sha256=_digest(a.get("digest")),
            )
            for a in data.get("assets") or []
        )
        return Release(
            tag=tag,
            name=str(data.get("name") or tag),
            published_at=str(data.get("published_at") or ""),
            prerelease=bool(data.get("prerelease")),
            assets=assets,
            zipball_url=str(data.get("zipball_url") or ""),
        )
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise _unexpected(f"bad release data: {exc}") from exc


def _digest(value: Any) -> Optional[str]:
    if isinstance(value, str) and value.lower().startswith("sha256:"):
        return value.split(":", 1)[1].lower()
    return None


class _NotFound(Exception):
    pass


class GitHubClient:
    def __init__(
        self,
        repo: str = REPO,
        urlopen: Optional[Callable[..., Any]] = None,
        timeout: float = 20.0,
        token: Optional[str] = None,
    ) -> None:
        self.repo = repo
        self._urlopen = urlopen or urllib.request.urlopen
        self.timeout = timeout
        self._token = token if token is not None else os.environ.get("GITHUB_TOKEN")

    def _request(self, url: str, api: bool) -> urllib.request.Request:
        if urlparse(url).scheme != "https":
            raise _unexpected(f"refusing non-HTTPS URL {url}")
        req = urllib.request.Request(url, headers={"User-Agent": f"deskbuddy-cli/{__version__}"})  # noqa: S310 (https checked)
        if api:
            req.add_header("Accept", "application/vnd.github+json")
            req.add_header("X-GitHub-Api-Version", "2022-11-28")
            if self._token and urlparse(url).hostname == API_HOST:
                # unredirected: urllib must not forward it if GitHub redirects elsewhere
                req.add_unredirected_header("Authorization", f"Bearer {self._token}")
        return req

    def _open(self, url: str, api: bool) -> Any:
        try:
            return self._urlopen(self._request(url, api), timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise _NotFound(url) from exc
            if exc.code in (403, 429):
                raise NetworkError(
                    "GitHub refused the request (API rate limit reached?)",
                    "Wait an hour, or set the GITHUB_TOKEN environment variable to a personal access token.",
                ) from exc
            raise NetworkError(f"GitHub answered HTTP {exc.code}", "Try again in a minute.") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise NetworkError(
                "Cannot reach GitHub",
                "Check your internet connection (and proxy/firewall), then try again.",
            ) from exc

    def get_json(self, path: str) -> Any:
        url = f"{API_ROOT}/repos/{self.repo}{path}"
        with self._open(url, api=True) as resp:
            body = resp.read(MAX_TEXT_BYTES + 1)
        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise _unexpected("not JSON") from exc

    def list_releases(self) -> list[Release]:
        try:
            data = self.get_json("/releases?per_page=100")
        except _NotFound as exc:
            raise NetworkError(
                f"Repository {self.repo} not found on GitHub", "Check your internet connection."
            ) from exc
        if not isinstance(data, list):
            raise _unexpected("release list is not a list")
        releases = [parse_release(item) for item in data if isinstance(item, dict) and not item.get("draft")]
        return sorted(releases, key=lambda r: version_key(r.tag), reverse=True)

    def get_release(self, tag: Optional[str]) -> Release:
        if tag is None:
            try:
                return parse_release(self.get_json("/releases/latest"))
            except _NotFound as exc:
                raise NetworkError(
                    "No firmware release has been published yet",
                    "Build from source instead: deskbuddy flash --local",
                ) from exc
        wanted = to_tag(tag)
        try:
            return parse_release(self.get_json(f"/releases/tags/{wanted}"))
        except _NotFound as exc:
            raise UsageError(f"Release {wanted} not found", "Run 'deskbuddy versions' to list the releases.") from exc

    def fetch_text(self, url: str) -> str:
        try:
            with self._open(url, api=False) as resp:
                body = resp.read(MAX_TEXT_BYTES + 1)
        except _NotFound as exc:
            raise NetworkError(f"Download failed: {url} not found", "Try again later.") from exc
        if len(body) > MAX_TEXT_BYTES:
            raise _unexpected("text file too large")
        return body.decode("utf-8", errors="replace")

    def download(
        self, url: str, dest: Path, expected_sha256: Optional[str] = None, progress: Optional[Progress] = None
    ) -> Path:
        """Stream `url` to `dest` atomically; verify sha256 if given. No partial files are left behind."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        part = dest.with_name(dest.name + ".part")
        try:
            self._stream_to(url, part, progress)
            if expected_sha256:
                verify_sha256(part, expected_sha256)
            os.replace(part, dest)
        finally:
            if part.exists():
                part.unlink()
        return dest

    def _stream_to(self, url: str, part: Path, progress: Optional[Progress]) -> None:
        try:
            with self._open(url, api=False) as resp, part.open("wb") as out:
                total = int(resp.headers.get("Content-Length") or 0)
                done = 0
                for block in iter(lambda: resp.read(_CHUNK), b""):
                    done += len(block)
                    if done > MAX_DOWNLOAD_BYTES:
                        raise IntegrityError("Download is unexpectedly large", "Report this on GitHub.")
                    out.write(block)
                    if progress and total:
                        progress(min(100.0, 100.0 * done / total))
        except _NotFound as exc:
            raise NetworkError(f"Download failed: {url} not found", "Try again later.") from exc
        except NetworkError as exc:
            raise NetworkError(f"Download failed: {exc.message}", exc.hint) from exc
        except OSError as exc:
            raise NetworkError(f"Download failed: {exc}", "Check your connection and free disk space.") from exc


def _safe_tag(tag: str) -> str:
    if not _TAG_RE.match(tag):
        raise IntegrityError(f"Refusing unusual release tag {tag!r}", "Report this on GitHub.")
    return tag


def expected_image_sha256(release: Release, asset: Asset, client: GitHubClient) -> str:
    """sha256 for `asset` from the release's SHA256SUMS, cross-checked against GitHub's own digest."""
    from_sums: Optional[str] = None
    sums_asset = release.asset(SUMS_NAME)
    if sums_asset is not None:
        from_sums = parse_sha256sums(client.fetch_text(sums_asset.url)).get(asset.name)
    if from_sums and asset.sha256 and from_sums != asset.sha256:
        raise IntegrityError(
            f"Checksums for {asset.name} disagree (SHA256SUMS vs GitHub)",
            "The release may have been tampered with. Do not flash it; report this on GitHub.",
        )
    expected = from_sums or asset.sha256
    if not expected:
        raise IntegrityError(
            f"Release {release.tag} has no checksum for {asset.name}",
            "Refusing to flash an unverified image. Use --file with an image you trust, or --local.",
        )
    return expected


def fetch_firmware(
    release: Release, pio_env: str, cache_dir: Path, client: GitHubClient, progress: Optional[Progress] = None
) -> Path:
    """Return a verified local copy of the release image for `pio_env` (downloads into the cache if needed)."""
    asset = release.image_for(pio_env)
    expected = expected_image_sha256(release, asset, client)
    path = cache_dir / _safe_tag(release.tag) / asset.name
    if path.is_file() and sha256_file(path) == expected:
        if progress:
            progress(100.0)
        return path
    return client.download(asset.url, path, expected, progress)


def _member_parts(name: str) -> list[str]:
    normalised = name.replace("\\", "/")
    if normalised.startswith("/") or re.match(r"^[A-Za-z]:", normalised):
        raise IntegrityError(
            f"Archive contains an unsafe path: {name}", "The archive was rejected; nothing was extracted."
        )
    parts = [p for p in PurePosixPath(normalised).parts if p not in ("", ".")]
    if ".." in parts:
        raise IntegrityError(
            f"Archive contains an unsafe path: {name}", "The archive was rejected; nothing was extracted."
        )
    return parts


def safe_extract_zip(archive: Path, dest: Path, strip_components: int = 1) -> Path:
    """Extract `archive` into `dest`, dropping the top `strip_components` folders.

    Every member is validated before anything is written: absolute paths, drive letters, '..'
    and symlinks are rejected, and the total size is capped.
    """
    if dest.exists() and any(dest.iterdir()):
        raise UsageError(f"{dest} already exists and is not empty", "Delete it or choose another --dest folder.")
    try:
        zf = zipfile.ZipFile(archive)
    except (zipfile.BadZipFile, OSError) as exc:
        raise IntegrityError(f"{archive.name} is not a valid zip archive", "Run the command again.") from exc
    with zf:
        plan: list[tuple[zipfile.ZipInfo, list[str]]] = []
        total = 0
        for info in zf.infolist():
            parts = _member_parts(info.filename)
            if stat.S_ISLNK(info.external_attr >> 16):
                raise IntegrityError(f"Archive contains a link ({info.filename})", "The archive was rejected.")
            total += info.file_size
            if total > MAX_EXTRACT_BYTES:
                raise IntegrityError("Archive is unexpectedly large", "The archive was rejected.")
            rel = parts[strip_components:]
            if rel:
                plan.append((info, rel))
        root = dest.resolve()
        for info, rel in plan:
            target = dest.joinpath(*rel)
            if root not in target.resolve().parents:
                raise IntegrityError(f"Archive contains an unsafe path: {info.filename}", "The archive was rejected.")
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, target.open("wb") as out:
                shutil.copyfileobj(src, out)
    return dest


def get_source(release: Release, dest_dir: Path, client: GitHubClient) -> Path:
    """Download the release's source archive and extract it to dest_dir/DeskBuddy-C3-<tag>/."""
    target = dest_dir / f"DeskBuddy-C3-{_safe_tag(release.tag)}"
    if not release.zipball_url:
        raise _unexpected("release has no source archive")
    with tempfile.TemporaryDirectory(prefix="deskbuddy-") as tmp:
        archive = client.download(release.zipball_url, Path(tmp) / "source.zip")
        return safe_extract_zip(archive, target)
