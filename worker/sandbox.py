from pprint import pprint

from tmp_jobs.id_format import change_id_format
from jobs.status import add_default_status
from services.signal import fetch_signal


def sandbox():
    s = fetch_signal(2)

    pprint(s)


if __name__ == "__main__":
    sandbox()
