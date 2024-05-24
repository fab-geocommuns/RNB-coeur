import csv

from batid.models import ADSAchievement
from batid.services.source import Source


def import_dgfip_ads_achievements(filename: str):
    """Import a single achievement file from DGFIP ADS.

    Args:
        filename (str): Name of the file to import.
    """

    src = Source("ads-dgfip")
    src.set_param("fname", filename)

    # read the csv file row by row
    with open(src.path, newline="") as f:
        for row in csv.DictReader(f, delimiter=";"):
            ADSAchievement.objects.create(
                file_number=row["Ads"],
                achieved_at=row["fin"],
            )
