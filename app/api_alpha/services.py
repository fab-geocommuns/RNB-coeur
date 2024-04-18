from batid.services.ads import get_cities
from batid.services.rnb_id import clean_rnb_id
from django.contrib.auth.models import User
from batid.services.ads import can_manage_ads_in_cities


class BuildingADS:
    OPERATIONS = ["build", "modify", "demolish"]


class BdgInADS:
    NEW_STR = "new"
    GUESS_STR = "guess"


def can_manage_ads_in_request(user: User, request_data) -> bool:
    cities = calc_ads_request_cities(request_data)
    return can_manage_ads_in_cities(user, cities)


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
