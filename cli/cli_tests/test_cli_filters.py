"""Мини-DSL фильтров: строка → термы; каждый класс синтаксических ошибок — с позицией."""

import pytest

from taskanline_cli.filters import FilterSyntaxError, Op, Term, parse


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("assignee:me", [Term("assignee", Op.IN, ("me",), 0)]),
        (
            "assignee:me state-type:started",
            [Term("assignee", Op.IN, ("me",), 0), Term("state-type", Op.IN, ("started",), 12)],
        ),
        ("label:bug,regression", [Term("label", Op.IN, ("bug", "regression"), 0)]),
        (
            "state-type:!completed,!canceled",
            [Term("state-type", Op.NIN, ("completed", "canceled"), 0)],
        ),
        ("priority:<=2", [Term("priority", Op.LTE, ("2",), 0)]),
        ("priority:>high", [Term("priority", Op.GT, ("high",), 0)]),
        ("due:<@today+7d", [Term("due", Op.LT, ("@today+7d",), 0)]),
        ("created:>=@week", [Term("created", Op.GTE, ("@week",), 0)]),
        ("due:2026-10-20", [Term("due", Op.IN, ("2026-10-20",), 0)]),
        ("title~логин", [Term("title", Op.CONTAINS, ("логин",), 0)]),
        ('title~"два слова"', [Term("title", Op.CONTAINS, ("два слова",), 0)]),
        ('state:"In Progress",Todo', [Term("state", Op.IN, ("In Progress", "Todo"), 0)]),
        ("assignee:null", [Term("assignee", Op.IS_NULL, (), 0)]),
        ("parent:!null", [Term("parent", Op.NOT_NULL, (), 0)]),
        ("project:019a5c1e", [Term("project", Op.IN, ("019a5c1e",), 0)]),
        ("   ", []),
    ],
)
def test_parses(text: str, expected: list[Term]) -> None:
    assert parse(text) == expected


@pytest.mark.parametrize(
    ("text", "position", "message", "suggestion"),
    [
        ("assignee:me asignee:you", 12, "неизвестное поле «asignee»", "assignee"),
        ("stat:Todo", 0, "неизвестное поле «stat»", "state"),
        ("bogus", 0, "ожидалось поле:значение, получено «bogus»", None),
        ("assignee:", 9, "пустое значение поля «assignee»", None),
        ("label:bug label:ui", 10, "поле «label» указано дважды", None),
        ("state~Todo", 5, "подстрока «~» допустима только для title", None),
        ("title:логин", 5, "title ищется подстрокой", "title~логин"),
        ("label:>2", 6, "сравнение недопустимо для поля «label»", None),
        ("label:null", 6, "поле «label» не бывает пустым", None),
        ("label:bug,!ui", 6, "отрицание — у всех значений поля или ни у одного", None),
        ("label:bug,", 6, "пустое значение в списке поля «label»", None),
        ("state-type:startd", 11, "неизвестный тип статуса «startd»", "started"),
        ("priority:critical", 9, "приоритет — none, urgent, high, medium, low или 0–4, "
         "получено «critical»", None),
        ("due:<завтра", 5, "ожидалась дата YYYY-MM-DD, @today±Nd или @week, получено «завтра»",
         None),
        ("due:2026-10-01,2026-10-02", 4, "поле «due» сравнивается с одной датой: due:>@today",
         None),
    ],
)  # fmt: skip
def test_errors_point_at_position(
    text: str, position: int, message: str, suggestion: str | None
) -> None:
    with pytest.raises(FilterSyntaxError) as caught:
        parse(text)

    assert (caught.value.position, caught.value.message, caught.value.suggestion) == (
        position,
        message,
        suggestion,
    )


def test_error_rendering_matches_spec() -> None:
    with pytest.raises(FilterSyntaxError) as caught:
        parse("assignee:me asignee:you")

    assert caught.value.render() == (
        "Ошибка в фильтре на позиции 12: неизвестное поле «asignee».\n"
        "  assignee:me asignee:you\n"
        "              ^\n"
        "Возможно, вы имели в виду: assignee"
    )
