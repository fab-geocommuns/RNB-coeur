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


def ext_ids_equal(ext_ids1: list[dict], ext_ids2: list[dict]) -> bool:

    if not isinstance(ext_ids1, list) or not isinstance(ext_ids2, list):
        return False
    if len(ext_ids1) != len(ext_ids2):
        return False

    def _ext_id_to_str(ext_id: dict) -> str:
        return f"{ext_id.get('source', '')}//{ext_id.get('id', '')}//{ext_id.get('source_version', '')}//{ext_id.get('created_at', '')}"

    ext_ids1_str = sorted(_ext_id_to_str(ext_id) for ext_id in ext_ids1)
    ext_ids2_str = sorted(_ext_id_to_str(ext_id) for ext_id in ext_ids2)

    return ext_ids1_str == ext_ids2_str
