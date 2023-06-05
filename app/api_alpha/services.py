import json

from batid.models import City
from django.conf import settings
from django.db import connection
from batid.services.rnb_id import clean_rnb_id


class BuildingADS:
    OPERATIONS = ["build", "modify", "demolish"]


class BdgInADS:
    NEW_STR = "new"


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
        if op["building"]["rnb_id"] == BdgInADS.NEW_STR:
            if op["building"]["geometry"]["type"] == "Point":
                # Add the op point to the multipoints
                multipoints["coordinates"].append(
                    op["building"]["geometry"]["coordinates"]
                )

            elif op["building"]["geometry"]["type"] == "MultiPolygon":
                # Add each polygon of each op multipolygon to the multipolygon
                for poly in op["building"]["geometry"]["coordinates"]:
                    multipolygons["coordinates"].append(poly)

        else:
            rnb_ids.append(clean_rnb_id(op["building"]["rnb_id"]))

    """
        Toutes les villes qui soient : 
        - continennet un batiment dont le rnb_id est dans la liste des rnb_id
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
        "db_srid": settings.DEFAULT_SRID,
    }
    cities = City.objects.raw(q, params)

    return [c for c in cities]
