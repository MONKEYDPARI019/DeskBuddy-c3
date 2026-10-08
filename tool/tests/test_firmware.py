from __future__ import annotations

import hashlib
import json

import pytest

from deskbuddy import esptool_compat, firmware
from deskbuddy.errors import BuildError
from deskbuddy.esptool_compat import EsptoolResult

V4 = esptool_compat.syntax_for(4)
V5 = esptool_compat.syntax_for(5)


def make_build(tmp_path, env="c3", boot_offset="0x0", app_offset="0x10000"):
    build = tmp_path / "project" / ".pio" / "build" / env
    build.mkdir(parents=True)
    for name in ("bootloader.bin", "partitions.bin", "boot_app0.bin", "firmware.bin"):
        (build / name).write_bytes(b"\xe9" + name.encode())
    (build / "firmware.elf").write_bytes(b"ELF")
    meta = {
        env: {
            "env_name": env,
            "prog_path": str(build / "firmware.elf"),
            "extra": {
                "flash_images": [
                    {"offset": boot_offset, "path": str(build / "bootloader.bin")},
                    {"offset": "0x8000", "path": str(build / "partitions.bin")},
                    {"offset": "0xe000", "path": str(build / "boot_app0.bin")},
                ],
                "application_offset": app_offset,
            },
        }
    }
    return build, meta


def make_project(tmp_path, version="c3-2.0.0"):
    project = tmp_path / "project"
    (project / "src").mkdir(parents=True, exist_ok=True)
    (project / "src" / "config.h").write_text(f'#define FW_VERSION "{version}"\n')
    (project / "platformio.ini").write_text("[platformio]\n")
    return project


def test_flash_images_from_metadata(tmp_path):
    build, meta = make_build(tmp_path)
    images = firmware.flash_images(meta, "c3")
    assert [(hex(i.offset), i.path.name) for i in images] == [
        ("0x0", "bootloader.bin"),
        ("0x8000", "partitions.bin"),
        ("0xe000", "boot_app0.bin"),
        ("0x10000", "firmware.bin"),
    ]


def test_flash_images_rejects_wrong_bootloader_offset(tmp_path):
    _, meta = make_build(tmp_path, boot_offset="0x1000")
    with pytest.raises(BuildError, match="bootloader"):
        firmware.flash_images(meta, "c3")


def test_flash_images_rejects_wrong_app_offset(tmp_path):
    _, meta = make_build(tmp_path, app_offset="0x20000")
    with pytest.raises(BuildError, match="0x10000"):
        firmware.flash_images(meta, "c3")


def test_flash_images_missing_env(tmp_path):
    _, meta = make_build(tmp_path)
    with pytest.raises(BuildError, match="no metadata"):
        firmware.flash_images(meta, "c3-battery")


def test_flash_images_missing_file(tmp_path):
    build, meta = make_build(tmp_path)
    (build / "boot_app0.bin").unlink()
    with pytest.raises(BuildError, match="missing"):
        firmware.flash_images(meta, "c3")


def test_parse_metadata_output_skips_noise():
    text = 'Some warning\n{"c3": {"prog_path": "x"}}\n'
    assert firmware.parse_metadata_output(text) == {"c3": {"prog_path": "x"}}
    with pytest.raises(BuildError):
        firmware.parse_metadata_output("no json here")


def test_merge_args_v4_and_v5(tmp_path):
    _, meta = make_build(tmp_path)
    images = firmware.flash_images(meta, "c3")
    args5 = firmware.merge_args(V5, images, tmp_path / "out.bin")
    assert args5[:9] == ["--chip", "esp32c3", "merge-bin", "-o", str(tmp_path / "out.bin"), "-fm", "dio", "-fs", "4MB"]
    assert args5[9:11] == ["0x0", str(images[0].path)]
    assert firmware.merge_args(V4, images, tmp_path / "o.bin")[2] == "merge_bin"


class FakeTools:
    def __init__(self, meta, build_rc=0, merge_rc=0):
        self.meta = meta
        self.build_rc = build_rc
        self.merge_rc = merge_rc
        self.commands = []

    def runner(self, cmd, cwd=None, env=None, on_line=None):
        self.commands.append(cmd)
        if "metadata" in cmd:
            on_line("Processing c3")
            on_line(json.dumps(self.meta))
            return 0
        on_line("Building...")
        return self.build_rc

    def esptool(self, args, on_line=None):
        out = args[args.index("-o") + 1]
        with open(out, "wb") as fh:
            fh.write(b"\xe9merged")
        return EsptoolResult(self.merge_rc, "merged" if self.merge_rc == 0 else "A fatal error occurred: boom")


def test_build_and_merge(tmp_path):
    project = make_project(tmp_path)
    _, meta = make_build(tmp_path)
    tools = FakeTools(meta)
    merged = firmware.build_and_merge(
        project,
        "c3",
        tmp_path / "dist",
        pio_cmd=["pio"],
        env={"X": "1"},
        runner=tools.runner,
        esptool_runner=tools.esptool,
        syntax=V5,
    )
    assert merged.path == tmp_path / "dist" / "deskbuddy-c3-c3-v2.0.0.bin"
    assert merged.sha256 == hashlib.sha256(b"\xe9merged").hexdigest()
    assert merged.size == len(b"\xe9merged") and merged.version == "2.0.0" and merged.env == "c3"
    assert tools.commands[0] == ["pio", "run", "-e", "c3"]
    assert tools.commands[1] == ["pio", "project", "metadata", "-e", "c3", "--json-output"]


def test_build_failure_shows_tail(tmp_path):
    project = make_project(tmp_path)
    _, meta = make_build(tmp_path)
    with pytest.raises(BuildError, match="build failed") as excinfo:
        firmware.build_and_merge(
            project,
            "c3",
            tmp_path / "dist",
            pio_cmd=["pio"],
            env=None,
            runner=FakeTools(meta, build_rc=1).runner,
            esptool_runner=None,
            syntax=V5,
        )
    assert "Building..." in excinfo.value.hint


def test_merge_failure(tmp_path):
    project = make_project(tmp_path)
    _, meta = make_build(tmp_path)
    tools = FakeTools(meta, merge_rc=2)
    with pytest.raises(BuildError, match="merge"):
        firmware.build_and_merge(
            project,
            "c3",
            tmp_path / "dist",
            pio_cmd=["pio"],
            env=None,
            runner=tools.runner,
            esptool_runner=tools.esptool,
            syntax=V5,
        )


def test_write_release_files(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "deskbuddy-c3-c3-v2.0.0.bin").write_bytes(b"usb")
    (dist / "deskbuddy-c3-c3-battery-v2.0.0.bin").write_bytes(b"battery")
    (dist / "deskbuddy-c3-c3-v1.0.0.bin").write_bytes(b"old")  # other versions are ignored
    sums, manifest = firmware.write_release_files(dist, "2.0.0", tool_min_version="2.0.0")
    lines = sums.read_text().splitlines()
    assert lines == [
        f"{hashlib.sha256(b'battery').hexdigest()}  deskbuddy-c3-c3-battery-v2.0.0.bin",
        f"{hashlib.sha256(b'usb').hexdigest()}  deskbuddy-c3-c3-v2.0.0.bin",
    ]
    data = json.loads(manifest.read_text())
    assert data["version"] == "2.0.0" and data["tool_min_version"] == "2.0.0" and data["chip"] == "esp32c3"
    assert data["images"] == [
        {
            "env": "c3",
            "build": "usb",
            "file": "deskbuddy-c3-c3-v2.0.0.bin",
            "sha256": hashlib.sha256(b"usb").hexdigest(),
            "size": 3,
            "chip": "esp32c3",
            "offset": "0x0",
        },
        {
            "env": "c3-battery",
            "build": "battery",
            "file": "deskbuddy-c3-c3-battery-v2.0.0.bin",
            "sha256": hashlib.sha256(b"battery").hexdigest(),
            "size": 7,
            "chip": "esp32c3",
            "offset": "0x0",
        },
    ]


def test_write_release_files_needs_images(tmp_path):
    with pytest.raises(BuildError, match="No firmware images"):
        firmware.write_release_files(tmp_path, "2.0.0")
