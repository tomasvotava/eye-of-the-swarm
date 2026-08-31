import pytest

from eye.tui._input import next_line, parse_bounded_index


def test_next_line_returns_the_next_value() -> None:
    assert next_line(iter(["1"]), "component") == "1"


def test_next_line_raises_a_named_runtime_error_on_exhaustion() -> None:
    with pytest.raises(RuntimeError, match="component has no more input to consume"):
        next_line(iter([]), "component")


def test_parse_bounded_index_returns_zero_based_index() -> None:
    assert parse_bounded_index("1", 3) == 0
    assert parse_bounded_index("3", 3) == 2


def test_parse_bounded_index_rejects_out_of_range() -> None:
    assert parse_bounded_index("0", 3) is None
    assert parse_bounded_index("4", 3) is None


def test_parse_bounded_index_rejects_non_ascii_digits() -> None:
    assert parse_bounded_index("②", 3) is None


def test_parse_bounded_index_rejects_non_numeric_input() -> None:
    assert parse_bounded_index("abc", 3) is None
