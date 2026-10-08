from __future__ import annotations

import hashlib
import io
import json
import stat
import urllib.error
import urllib.request
import zipfile

import pytest

from deskbuddy import checksums, github
from deskbuddy.errors import IntegrityError, NetworkError, UsageError

IMG_USB = b"\xe9" + b"U" * 100
IMG_BAT = b"\xe9" + b"B" * 100
SUMS = (
    f"{hashlib.sha256(IMG_USB).hexdigest()}  deskbuddy-c3-c3-v2.0.0.bin\n"
    f"{hashlib.sha256(IMG_BAT).hexdigest()} *deskbuddy-c3-c3-battery-v2.0.0.bin\n"
)
DL = "https://github.com/MONKEYDPARI019/DeskBuddy-C3/releases/download/v2.0.0/"


def release_json(tag="v2.0.0", draft=False, prerelease=False, with_sums=True, digest_usb=None):
    assets = [
        {
            "name": "deskbuddy-c3-c3-v2.0.0.bin",
            "size": len(IMG_USB),
            "browser_download_url": DL + "usb",
            "digest": digest_usb,
        },
        {"name": "deskbuddy-c3-c3-battery-v2.0.0.bin", "size": len(IMG_BAT), "browser_download_url": DL + "bat"},
        {"name": "manifest.json", "size": 10, "browser_download_url": DL + "manifest"},
    ]
    if with_sums:
        assets.append({"name": "SHA256SUMS", "size": len(SUMS), "browser_download_url": DL + "sums"})
    return {
        "tag_name": tag,
        "name": f"DeskBuddy C3 {tag}",
        "published_at": "2026-10-08T12:00:00Z",
        "draft": draft,
        "prerelease": prerelease,
        "assets": assets,
        "zipball_url": f"https://api.github.com/repos/MONKEYDPARI019/DeskBuddy-C3/zipball/{tag}",
    }


class FakeResponse(io.BytesIO):
    def __init__(self, body: bytes, headers=None):
        super().__init__(body)
        self.headers = headers or {"Content-Length": str(len(body))}


class FakeWeb:
    """Maps URL -> bytes | Exception; records each Request."""

    def __init__(self, routes):
        self.routes = routes
        self.requests = []

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        item = self.routes.get(request.full_url)
        if item is None:
            raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, None)
        if isinstance(item, Exception):
            raise item
        return FakeResponse(item)


API = "https://api.github.com/repos/MONKEYDPARI019/DeskBuddy-C3"


def make_client(routes, token=None):
    return github.GitHubClient(urlopen=FakeWeb(routes), token=token)


# --- checksums ------------------------------------------------------------------


def test_parse_sha256sums_text_and_binary_markers():
    sums = checksums.parse_sha256sums(SUMS + "\n# comment\nnot a line\n")
    assert sums["deskbuddy-c3-c3-v2.0.0.bin"] == hashlib.sha256(IMG_USB).hexdigest()
    assert sums["deskbuddy-c3-c3-battery-v2.0.0.bin"] == hashlib.sha256(IMG_BAT).hexdigest()
    assert len(sums) == 2


def test_format_sha256sums_round_trip():
    text = checksums.format_sha256sums({"b.bin": "b" * 64, "a.bin": "a" * 64})
    assert text == f"{'a' * 64}  a.bin\n{'b' * 64}  b.bin\n"
    assert checksums.parse_sha256sums(text) == {"a.bin": "a" * 64, "b.bin": "b" * 64}


def test_verify_sha256(tmp_path):
    path = tmp_path / "x.bin"
    path.write_bytes(IMG_USB)
    checksums.verify_sha256(path, hashlib.sha256(IMG_USB).hexdigest().upper())
    with pytest.raises(IntegrityError, match="checksum"):
        checksums.verify_sha256(path, "0" * 64)


# --- release parsing / selection -----------------------------------------------


def test_parse_release():
    rel = github.parse_release(release_json(digest_usb="sha256:" + "ab" * 32))
    assert rel.tag == "v2.0.0"
    assert rel.date == "2026-10-08"
    assert [a.name for a in rel.assets][:2] == ["deskbuddy-c3-c3-v2.0.0.bin", "deskbuddy-c3-c3-battery-v2.0.0.bin"]
    assert rel.assets[0].sha256 == "ab" * 32
    assert rel.assets[1].sha256 is None


def test_image_for_env_does_not_confuse_c3_and_c3_battery():
    rel = github.parse_release(release_json())
    assert rel.image_for("c3").name == "deskbuddy-c3-c3-v2.0.0.bin"
    assert rel.image_for("c3-battery").name == "deskbuddy-c3-c3-battery-v2.0.0.bin"


def test_image_for_missing_env():
    data = release_json()
    data["assets"] = [a for a in data["assets"] if "battery" not in a["name"]]
    with pytest.raises(UsageError, match="has no battery firmware"):
        github.parse_release(data).image_for("c3-battery")


def test_list_releases_sorted_and_without_drafts():
    routes = {
        API + "/releases?per_page=100": json.dumps(
            [
                release_json("v1.0.0"),
                release_json("v2.0.0"),
                release_json("v3.0.0", draft=True),
                release_json("v2.1.0-rc1", prerelease=True),
            ]
        ).encode()
    }
    tags = [r.tag for r in make_client(routes).list_releases()]
    assert tags == ["v2.1.0-rc1", "v2.0.0", "v1.0.0"]


def test_get_latest_release():
    client = make_client({API + "/releases/latest": json.dumps(release_json()).encode()})
    assert client.get_release(None).tag == "v2.0.0"


def test_get_release_by_tag_accepts_bare_version():
    client = make_client({API + "/releases/tags/v2.0.0": json.dumps(release_json()).encode()})
    assert client.get_release("2.0.0").tag == "v2.0.0"


def test_get_release_unknown_tag():
    with pytest.raises(UsageError, match="v9.9.9 not found"):
        make_client({}).get_release("v9.9.9")


def test_get_latest_when_no_release_exists():
    with pytest.raises(NetworkError, match="No firmware release"):
        make_client({}).get_release(None)


def test_rate_limit_message():
    err = urllib.error.HTTPError(API + "/releases/latest", 403, "rate limit exceeded", {}, None)
    with pytest.raises(NetworkError, match="rate limit") as excinfo:
        make_client({API + "/releases/latest": err}).get_release(None)
    assert "GITHUB_TOKEN" in excinfo.value.hint


def test_offline_message():
    err = urllib.error.URLError("getaddrinfo failed")
    with pytest.raises(NetworkError, match="Cannot reach GitHub"):
        make_client({API + "/releases/latest": err}).get_release(None)


def test_bad_json_is_a_network_error():
    with pytest.raises(NetworkError, match="unexpected answer"):
        make_client({API + "/releases/latest": b"<html>"}).get_release(None)


def test_token_only_sent_to_api_host(tmp_path):
    routes = {API + "/releases/latest": json.dumps(release_json()).encode(), DL + "usb": IMG_USB}
    client = make_client(routes, token="secret-token")
    client.get_release(None)
    client.download(DL + "usb", tmp_path / "x.bin")
    api_req, dl_req = client._urlopen.requests
    assert api_req.get_header("Authorization") == "Bearer secret-token"
    assert dl_req.get_header("Authorization") is None
    assert dl_req.get_header("User-agent").startswith("deskbuddy-cli/")


# --- downloads ------------------------------------------------------------------


def test_download_verifies_and_reports_progress(tmp_path):
    seen = []
    client = make_client({DL + "usb": IMG_USB})
    out = client.download(DL + "usb", tmp_path / "a" / "x.bin", hashlib.sha256(IMG_USB).hexdigest(), seen.append)
    assert out.read_bytes() == IMG_USB
    assert seen[-1] == pytest.approx(100.0)


def test_download_bad_checksum_leaves_no_file(tmp_path):
    client = make_client({DL + "usb": IMG_USB})
    with pytest.raises(IntegrityError):
        client.download(DL + "usb", tmp_path / "x.bin", "0" * 64)
    assert list(tmp_path.iterdir()) == []


def test_download_network_failure(tmp_path):
    client = make_client({DL + "usb": urllib.error.URLError("reset")})
    with pytest.raises(NetworkError, match="Download failed"):
        client.download(DL + "usb", tmp_path / "x.bin")


def _firmware_routes(sums=SUMS, image=IMG_USB):
    return {DL + "sums": sums.encode(), DL + "usb": image}


def test_fetch_firmware_downloads_and_caches(tmp_path):
    rel = github.parse_release(release_json())
    client = make_client(_firmware_routes())
    path = github.fetch_firmware(rel, "c3", tmp_path, client)
    assert path == tmp_path / "v2.0.0" / "deskbuddy-c3-c3-v2.0.0.bin"
    assert path.read_bytes() == IMG_USB
    calls = len(client._urlopen.requests)
    again = github.fetch_firmware(rel, "c3", tmp_path, client)
    assert again == path
    assert len(client._urlopen.requests) == calls + 1  # only SHA256SUMS fetched again, image from cache


def test_fetch_firmware_replaces_corrupt_cache(tmp_path):
    rel = github.parse_release(release_json())
    cached = tmp_path / "v2.0.0" / "deskbuddy-c3-c3-v2.0.0.bin"
    cached.parent.mkdir(parents=True)
    cached.write_bytes(b"corrupt")
    path = github.fetch_firmware(rel, "c3", tmp_path, make_client(_firmware_routes()))
    assert path.read_bytes() == IMG_USB


def test_fetch_firmware_rejects_tampered_image(tmp_path):
    rel = github.parse_release(release_json())
    with pytest.raises(IntegrityError):
        github.fetch_firmware(rel, "c3", tmp_path, make_client(_firmware_routes(image=b"\xe9evil")))


def test_fetch_firmware_requires_a_checksum(tmp_path):
    rel = github.parse_release(release_json(with_sums=False))
    with pytest.raises(IntegrityError, match="no checksum"):
        github.fetch_firmware(rel, "c3", tmp_path, make_client(_firmware_routes()))


def test_fetch_firmware_uses_github_digest_when_sums_missing(tmp_path):
    rel = github.parse_release(
        release_json(with_sums=False, digest_usb="sha256:" + hashlib.sha256(IMG_USB).hexdigest())
    )
    path = github.fetch_firmware(rel, "c3", tmp_path, make_client(_firmware_routes()))
    assert path.read_bytes() == IMG_USB


def test_fetch_firmware_detects_digest_mismatch_with_sums(tmp_path):
    rel = github.parse_release(release_json(digest_usb="sha256:" + "0" * 64))
    with pytest.raises(IntegrityError, match="disagree"):
        github.fetch_firmware(rel, "c3", tmp_path, make_client(_firmware_routes()))


# --- safe extraction --------------------------------------------------------------


def make_zip(path, entries):
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in entries.items():
            if isinstance(data, zipfile.ZipInfo):
                zf.writestr(data, b"target")
            else:
                zf.writestr(name, data)
    return path


def test_safe_extract_strips_top_folder(tmp_path):
    archive = make_zip(
        tmp_path / "src.zip",
        {
            "MONKEYDPARI019-DeskBuddy-C3-abc123/README.md": b"hi",
            "MONKEYDPARI019-DeskBuddy-C3-abc123/firmware/src/main.cpp": b"int main(){}",
            "MONKEYDPARI019-DeskBuddy-C3-abc123/firmware/": b"",
        },
    )
    dest = github.safe_extract_zip(archive, tmp_path / "out" / "DeskBuddy-C3-v2.0.0")
    assert (dest / "README.md").read_bytes() == b"hi"
    assert (dest / "firmware" / "src" / "main.cpp").exists()


@pytest.mark.parametrize(
    "evil",
    ["top/../../evil.txt", "/etc/passwd", "C:/Windows/evil.txt", "top/..\\..\\evil.txt", "\\\\server\\share\\x"],
)
def test_safe_extract_rejects_traversal(tmp_path, evil):
    archive = make_zip(tmp_path / "evil.zip", {"top/ok.txt": b"ok", evil: b"pwned"})
    with pytest.raises(IntegrityError, match="unsafe path"):
        github.safe_extract_zip(archive, tmp_path / "out")
    assert not (tmp_path / "evil.txt").exists()
    assert not (tmp_path / "out").exists()


def test_safe_extract_rejects_symlinks(tmp_path):
    info = zipfile.ZipInfo("top/link")
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    archive = make_zip(tmp_path / "link.zip", {"top/link": info})
    with pytest.raises(IntegrityError, match="link"):
        github.safe_extract_zip(archive, tmp_path / "out")


def test_safe_extract_refuses_existing_non_empty_dest(tmp_path):
    archive = make_zip(tmp_path / "src.zip", {"top/a.txt": b"a"})
    dest = tmp_path / "out"
    dest.mkdir()
    (dest / "keep.txt").write_text("mine")
    with pytest.raises(UsageError, match="already exists"):
        github.safe_extract_zip(archive, dest)


def test_safe_extract_bad_zip(tmp_path):
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"not a zip")
    with pytest.raises(IntegrityError, match="not a valid zip"):
        github.safe_extract_zip(bad, tmp_path / "out")


def test_get_source(tmp_path):
    archive = make_zip(tmp_path / "src.zip", {"top/firmware/platformio.ini": b"[platformio]"})
    rel = github.parse_release(release_json())
    client = make_client({rel.zipball_url: archive.read_bytes()})
    dest = github.get_source(rel, tmp_path / "dest", client)
    assert dest == tmp_path / "dest" / "DeskBuddy-C3-v2.0.0"
    assert (dest / "firmware" / "platformio.ini").read_text() == "[platformio]"


def test_ping_ok_and_failures():
    make_client({"https://api.github.com/rate_limit": b"{}"}).ping()
    with pytest.raises(NetworkError, match="unexpected answer"):
        make_client({}).ping()
    with pytest.raises(NetworkError, match="Cannot reach GitHub"):
        make_client({"https://api.github.com/rate_limit": urllib.error.URLError("dns")}).ping()


def test_doctor_default_deps_use_ping():
    from deskbuddy import doctor

    deps = doctor.default_deps()
    assert deps.github_ping.__name__ == "ping"


def test_redirect_to_http_is_refused():
    handler = github._HttpsOnlyRedirects()
    req = urllib.request.Request("https://github.com/x")
    with pytest.raises(urllib.error.URLError, match="insecure redirect"):
        handler.redirect_request(req, None, 302, "Found", {}, "http://evil.example/x")
    ok = handler.redirect_request(req, None, 302, "Found", {}, "https://objects.githubusercontent.com/x")
    assert ok.full_url == "https://objects.githubusercontent.com/x"


@pytest.mark.parametrize("evil", ["top/file.txt:stream", "top/CON", "top/nul.txt", "top/trailing. "])
def test_safe_extract_rejects_windows_hostile_names(tmp_path, evil):
    archive = make_zip(tmp_path / "w.zip", {evil: b"x"})
    with pytest.raises(IntegrityError, match="unsafe path"):
        github.safe_extract_zip(archive, tmp_path / "out")


def test_asset_name_with_trailing_newline_is_not_an_image():
    from deskbuddy import envs

    assert envs.parse_image_filename("deskbuddy-c3-c3-v1.0.0.bin\n") is None
