import csv

from jobs.remove_light_bdgs import remove_light_bdgs
from logic.source import Source


def sandbox():
    dpt = "44"

    src = Source("bdnb_7")
    src.set_param("dpt", dpt)

    with open(src.find("batiment_construction.csv"), "r") as f:
        print("- list buildings")
        reader = csv.DictReader(f, delimiter=",")
        for row in list(reader)[:10]:
            print(row)


if __name__ == "__main__":
    sandbox()
