import csv

from batid.services.source import Source


def import_bdnd_2023_q4_bdgs(dpt):
    print("## Import BDNB 2023 Q4 buildings")

    src = Source("bdnb_2023_q4")
    src.set_param("dpt", dpt)

    candidates = []

    with open(src.find(f"{dpt}_bdgs.csv"), "r") as f:
        print("- list buildings")
        reader = csv.DictReader(f, delimiter=";")

    pass


def import_bdnd_2023_q4_addresses():
    pass
