import json
import os.path
from datetime import datetime

from batid.models import Building
from batid.services.source import Source


ACTIVE_BUILDING_COUNT = "active_building_count"


def all_stats():

    src = _get_source()

    # Check if the file exists, if not create it
    if not os.path.exists(src.path):
        json.dump({}, open(src.path, "w"))

    # Read and return
    with open(src.path, "r") as f:
        raw_data = json.load(f)

        # JSON does not handle dates, so we convert them back to datetime
        data = _convert_str_to_dates(raw_data)

        return data


def get_stat(key: str):

    if not isinstance(key, str):
        raise ValueError("Key must be a string")

    stats = all_stats()

    return stats.get(key, None)


def set_stat(key: str, value):

    if not isinstance(key, str):
        raise ValueError("Key must be a string")

    stats = all_stats()

    stats[key] = {"value": value, "calculated_at": datetime.now()}

    src = _get_source()

    with open(src.path, "w") as f:
        stats = _convert_dates_to_str(stats)
        json.dump(stats, f)

    return


def _get_source():
    return Source("cached_stats")


def get_path():
    return _get_source().path


def clear_stats():
    src = _get_source()

    if os.path.exists(src.path):
        os.remove(src.path)

    return


def _convert_str_to_dates(data):
    for key in data:
        if "calculated_at" in data[key]:
            data[key]["calculated_at"] = datetime.fromisoformat(
                data[key]["calculated_at"]
            )

    return data


def _convert_dates_to_str(data):
    for key in data:
        if "calculated_at" in data[key]:
            data[key]["calculated_at"] = data[key]["calculated_at"].isoformat()

    return data


def compute_stats():

    # Active building count
    count = Building.objects.filter(is_active=True).count()
    set_stat(ACTIVE_BUILDING_COUNT, count)
