from pathlib import Path

from deskbuddy.cmd_history import CommandHistory


def test_up_and_down_walk_through_earlier_commands():
    h = CommandHistory()
    for command in ("status", "help", "get"):
        h.add(command)
    assert h.older("") == "get"
    assert h.older("get") == "help"
    assert h.older("help") == "status"
    assert h.older("status") is None  # the oldest stays put
    assert h.newer() == "help"
    assert h.newer() == "get"
    assert h.newer() == ""  # past the newest: the (empty) new line
    assert h.newer() is None


def test_half_typed_text_comes_back_after_browsing():
    h = CommandHistory()
    h.add("status")
    assert h.older("face hap") == "status"
    assert h.newer() == "face hap"


def test_empty_history_does_nothing():
    h = CommandHistory()
    assert h.older("abc") is None
    assert h.newer() is None


def test_blank_and_repeated_commands_are_not_stored_twice():
    h = CommandHistory()
    for command in ("status", "  status ", "", "   ", "help", "status"):
        h.add(command)
    assert h.items == ["status", "help", "status"]


def test_sending_goes_back_to_the_new_line():
    h = CommandHistory()
    h.add("status")
    h.add("help")
    assert h.older("") == "help"
    assert h.older("help") == "status"
    h.add("status")  # sent again from history
    assert h.older("") == "status"  # starts again from the newest


def test_esc_reset_forgets_the_position():
    h = CommandHistory()
    h.add("status")
    h.add("help")
    h.older("draft")
    h.reset()
    assert h.older("") == "help"


def test_only_the_newest_commands_are_kept():
    h = CommandHistory(limit=3)
    for i in range(10):
        h.add(f"cmd {i}")
    assert h.items == ["cmd 7", "cmd 8", "cmd 9"]


def test_history_is_saved_and_loaded(tmp_path: Path):
    file = tmp_path / "sub" / "command_history.txt"
    h = CommandHistory(file)
    h.add("status")
    h.add("link ble")
    assert file.read_text(encoding="utf-8") == "status\nlink ble\n"
    again = CommandHistory(file)
    assert again.items == ["status", "link ble"]
    assert again.older("") == "link ble"


def test_loading_keeps_the_newest_and_skips_blank_lines(tmp_path: Path):
    file = tmp_path / "command_history.txt"
    file.write_text("a\n\n  \nb\nc\nd\n", encoding="utf-8")
    assert CommandHistory(file, limit=3).items == ["b", "c", "d"]


def test_a_broken_history_file_never_stops_anything(tmp_path: Path):
    unreadable = tmp_path / "command_history.txt"
    unreadable.write_bytes(b"\xff\xfe\xfa not utf-8")
    h = CommandHistory(unreadable)
    assert h.items == []
    blocked = tmp_path / "file-not-dir"
    blocked.write_text("x", encoding="utf-8")
    h = CommandHistory(blocked / "command_history.txt")  # its folder can't be created
    h.add("status")  # saving fails quietly
    assert h.items == ["status"]
