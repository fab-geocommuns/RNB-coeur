import json
from batid.models import City
from batid.services.ads import get_cities
from batid.services.rnb_id import clean_rnb_id


class BuildingADS:
    OPERATIONS = ["build", "modify", "demolish"]


class BdgInADS:
    NEW_STR = "new"
    GUESS_STR = "guess"


def calc_ads_request_cities(data):
    rnb_ids = []
    geojson_geometries = []

    for op in data["buildings_operations"]:

        # Check the rnb_id
        rnb_id = op.get("rnb_id", None)
        if rnb_id:
            rnb_ids.append(clean_rnb_id(rnb_id))

        # Check the geometry
        shape = op.get("shape", None)
        if shape:

            geojson_geometries.append(shape)

    return get_cities(rnb_ids, geojson_geometries)
