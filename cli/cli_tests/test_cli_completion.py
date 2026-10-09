"""Автодополнение bash, zsh и fish: Typer отвечает на запрос оболочки через окружение."""

import pytest

from cli_tests.conftest import Tkl


@pytest.mark.parametrize(
    ("shell", "env"),
    [
        ("bash", {"COMP_WORDS": "tkl ta", "COMP_CWORD": "1"}),
        ("zsh", {"_TYPER_COMPLETE_ARGS": "tkl ta"}),
        ("fish", {"_TYPER_COMPLETE_ARGS": "tkl ta", "_TYPER_COMPLETE_FISH_ACTION": "get-args"}),
    ],
)
def test_completes_commands(
    tkl: Tkl, monkeypatch: pytest.MonkeyPatch, shell: str, env: dict[str, str]
) -> None:
    monkeypatch.setenv("_TKL_COMPLETE", f"complete_{shell}")
    for name, value in env.items():
        monkeypatch.setenv(name, value)

    result = tkl()

    assert result.code == 0
    assert "task" in result.out


def test_install_option_is_offered(tkl: Tkl) -> None:
    assert "--install-completion" in tkl("--help").out
