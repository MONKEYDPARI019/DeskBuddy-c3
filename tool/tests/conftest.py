from __future__ import annotations

import pytest


class FakeClock:
    """Deterministic monotonic clock; sleep() advances time."""

    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("DESKBUDDY_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    return tmp_path / "home"
