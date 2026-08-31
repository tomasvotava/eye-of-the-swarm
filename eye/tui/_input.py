from collections.abc import Iterator


def next_line(input_source: Iterator[str], component: str) -> str:
    try:
        return next(input_source)
    except StopIteration:
        raise RuntimeError(f"{component} has no more input to consume") from None


def parse_bounded_index(raw: str, option_count: int) -> int | None:
    try:
        value = int(raw.strip())
    except ValueError:
        return None
    if not 1 <= value <= option_count:
        return None
    return value - 1
