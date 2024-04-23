import json

from django.contrib.auth.models import User
from django.contrib.gis.geos import GEOSException
from django.contrib.gis.geos import GEOSGeometry
from rest_framework.exceptions import ValidationError

from batid.services.ads import can_manage_ads_in_cities
from batid.services.ads import get_cities
from batid.services.rnb_id import clean_rnb_id


class BuildingADS:
    OPERATIONS = ["build", "modify", "demolish"]


def can_manage_ads_in_request(user: User, request_data) -> bool:
    cities = calc_ads_request_cities(request_data)
    return can_manage_ads_in_cities(user, cities)


def calc_ads_request_cities(data):

    cities = []

    if "buildings_operations" in data:

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

                # We have to check if the shape is a valid geojson.
                # It is hacky but the DRF structure dont let us validate data before permission check
                try:
                    GEOSGeometry(json.dumps(shape))
                    geojson_geometries.append(shape)
                except (ValueError, GEOSException):
                    raise ValidationError(
                        {"buildings_operations": ["Invalid GeoJSON geometry"]}
                    )

        cities = get_cities(rnb_ids, geojson_geometries)

    return cities
