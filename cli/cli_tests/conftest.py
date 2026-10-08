"""Фикстуры CLI: изолированный конфиг, поддельное API и вызов `tkl` как процесса."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest

from cli_tests.fake_api import FakeApi
from taskanline_cli import context
from taskanline_cli.app import main


@dataclass
class Run:
    code: int
    out: str
    err: str


Tkl = Callable[..., Run]


@pytest.fixture
def api() -> FakeApi:
    return FakeApi()


@pytest.fixture
def config_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for name in ("TKL_TOKEN", "TKL_API_URL", "TKL_PROFILE", "TKL_WORKSPACE", "TKL_TEAM",
                 "TKL_OUTPUT", "NO_COLOR"):  # fmt: skip
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def tkl(
    api: FakeApi,
    config_home: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[Tkl]:
    monkeypatch.setattr(context, "TRANSPORT", lambda: httpx.MockTransport(api.handle))
    monkeypatch.setattr(context, "CLIENT_OPTIONS", {"max_retries": 0})
    monkeypatch.setenv("TKL_TOKEN", "tkl_test_token")
    monkeypatch.setenv("TKL_API_URL", "http://tkl.test")

    def invoke(*args: str) -> Run:
        code = main(list(args))
        captured = capsys.readouterr()
        return Run(code, captured.out, captured.err)

    yield invoke
