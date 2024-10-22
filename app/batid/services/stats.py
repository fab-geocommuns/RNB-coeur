import json
import os.path

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
        return json.load(f)

def get_stat(key:str):

    if not isinstance(key, str):
        raise ValueError("Key must be a string")

    stats = all_stats()

    return stats.get(key, None)

def set_stat(key:str, value):

    if not isinstance(key, str):
        raise ValueError("Key must be a string")


    stats = all_stats()

    stats[key] = value

    src = _get_source()

    with open(src.path, "w") as f:
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


def fetch_stats():

    # Active building count
    count = Building.objects.filter(is_active=True).count()
    set_stat(ACTIVE_BUILDING_COUNT, count)