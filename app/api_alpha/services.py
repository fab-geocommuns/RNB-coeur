import json

from rest_framework import exceptions
from rest_framework import serializers

from api_alpha.permissions import ADSCityPermission
from batid.models import City
from batid.services.rnb_id import clean_rnb_id


class BuildingADS:
    OPERATIONS = ["build", "modify", "demolish"]


class BdgInADS:
    NEW_STR = "new"
    GUESS_STR = "guess"


def calc_ads_cities(data):
    rnb_ids = []
    multipoints = {
        "type": "MultiPoint",
        "coordinates": [],
    }
    multipolygons = {
        "type": "MultiPolygon",
        "coordinates": [],
    }

    for op in data["buildings_operations"]:

        # Check the rnb_id
        rnb_id = op.get("rnb_id", None)
        if rnb_id:
            rnb_ids.append(clean_rnb_id(rnb_id))

        # Check the geometry
        shape = op.get("shape", None)
        if shape:

            if shape["type"] == "Point":
                multipoints["coordinates"].append(shape["coordinates"])

            elif shape["type"] == "MultiPolygon":
                for poly in op["shape"]["coordinates"]:
                    multipolygons["coordinates"].append(poly)

    """
        Toutes les villes qui soit :
        - contiennent un batiment dont le rnb_id est dans la liste des rnb_id
        - soit contiennent un point dans la liste des points
        - soit contiennent un multipolygone dans la liste des multipolygones
    """
    wheres = []

    if rnb_ids:
        wheres.append(
            "EXISTS (SELECT 1 FROM batid_building as b WHERE b.rnb_id IN %(rnb_ids)s AND ST_Intersects(b.point, c.shape))"
        )

    if multipoints["coordinates"]:
        wheres.append(
            "ST_Intersects(ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%(multipoints)s), 4326), %(db_srid)s), c.shape)"
        )

    if multipolygons["coordinates"]:
        wheres.append(
            "ST_Intersects(ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%(multipolygons)s), 4326), %(db_srid)s), c.shape)"
        )

    wheres_str = " OR ".join(wheres)

    q = (
        "SELECT c.id, c.code_insee, c.name FROM batid_city as c "
        f"WHERE {wheres_str} "
        "ORDER BY c.code_insee"
    )
    params = {
        "rnb_ids": tuple(rnb_ids),
        "multipoints": json.dumps(multipoints),
        "multipolygons": json.dumps(multipolygons),
        "db_srid": 4326,
    }
    cities = City.objects.raw(q, params)

    return [c for c in cities]


def get_city_from_request(data, user, view):
    cities = calc_ads_cities(data)

    # First we validate we have only one city

    if len(cities) == 0:
        raise serializers.ValidationError(
            {"buildings_operations": ["Buildings are in an unknown city"]}
        )

    if len(cities) > 1:
        raise serializers.ValidationError(
            {"buildings_operations": ["Buildings must be in only one city"]}
        )

    city = cities[0]

    # Then we do permission

    perm = ADSCityPermission()

    if not perm.user_has_permission(city, user, view):
        raise exceptions.PermissionDenied(detail="You can not edit ADS in this city.")

    return city
