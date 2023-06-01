from tmp_jobs.id_format import change_id_format
from jobs.status import add_default_status


def sandbox():
    print("---- SANDBOX ----")
    c = add_default_status()
    print(c)


if __name__ == "__main__":
    sandbox()
