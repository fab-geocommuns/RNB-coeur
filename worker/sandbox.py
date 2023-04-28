import csv

from jobs.export import export_city
from logic.source import Source


def sandbox():
    export_city("38185")


if __name__ == "__main__":
    sandbox()
