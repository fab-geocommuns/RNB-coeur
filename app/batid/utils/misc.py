from collections.abc import Iterable
from typing import Any
from typing import Callable


def is_float(string: str) -> bool:
    try:
        float(string)
        return True
    except ValueError:
        return False


def max_by_group(
    iterable: Iterable, max_key: Callable, group_key: Callable
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for item in iterable:
        group = group_key(item)
        if group not in result or max_key(result[group]) < max_key(item):
            result[group] = item
    return result
