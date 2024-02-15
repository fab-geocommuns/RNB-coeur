import concurrent.futures
import sys

from batid.services.closest_bdg import get_closest


def pair(data, strategy="closest"):
    __validate_strategy(strategy)
    __validate_data(data)

    return __do_pairing(data, strategy)


def __validate_strategy(strategy):
    # Check the function linked to this strategy exists
    if not hasattr(sys.modules[__name__], __strategy_fn_name(strategy)):
        raise Exception(f"Unknown strategy {strategy}")


def __strategy_fn_name(strategy):
    return f"__do_one_{strategy}"


def __do_one_closest(row):
    match = get_closest(row["lat"], row["lng"], row["radius"])
    return row, match


def __do_pairing(data, strategy) -> dict:
    strat_fn = getattr(sys.modules[__name__], __strategy_fn_name(strategy))

    results = {}
    with concurrent.futures.ThreadPoolExecutor() as executor:
        tasks = [executor.submit(strat_fn, row) for row in data]

        for future in concurrent.futures.as_completed(tasks):
            params, pairing = future.result()
            results[params["ext_id"]] = {
                "params": params,
                "result": pairing,
            }

        return results


def __validate_data(data):
    __validate_types(data)
    __validate_ext_ids(data)


def __validate_types(data):
    for row in data:
        if not isinstance(row, dict):
            raise Exception("data must be a list of dicts")

        if "ext_id" not in row:
            raise Exception("ext_id is required for each row")


def __validate_ext_ids(data):
    ext_ids = [d["ext_id"] for d in data]
    if len(ext_ids) != len(set(ext_ids)):
        raise Exception("ext_ids are not unique")
