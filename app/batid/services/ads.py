from django.contrib.auth.models import User
from django.contrib.gis.geos import GEOSGeometry

from batid.models import ADS
from batid.models import City


def get_managed_insee_codes(user: User) -> list:
    codes = []
    for org in user.organizations.all():
        codes += org.managed_cities

    return list(set(codes))


def can_manage_ads_in_cities(user: User, cities: list) -> bool:

    if len(cities) == 0:
        return False

    managed_insee_codes = get_managed_insee_codes(user)

    if len(managed_insee_codes) == 0:
        return False

    for city in cities:
        if city.code_insee not in managed_insee_codes:
            return False

    return True


def can_manage_ads(user: User, ads: ADS) -> bool:

    rnb_ids = []
    geojson_geometries = []

    for op in ads.buildings_operations.all():
        rnb_id = op.rnb_id
        if rnb_id:
            rnb_ids.append(rnb_id)

        shape = op.shape
        if shape:
            geojson_geometries.append(shape)

    cities = get_cities(rnb_ids, geojson_geometries)

    return can_manage_ads_in_cities(user, cities)


def get_cities(rnb_ids: list, geojson_geometries: list[GEOSGeometry]) -> list:

    if not rnb_ids and not geojson_geometries:
        return []

    wheres = []
    params = []

    if rnb_ids:
        wheres.append(
            "EXISTS (SELECT 1 FROM batid_building as b WHERE b.rnb_id IN %s AND ST_Intersects(b.point, c.shape))"
        )
        params.append(tuple(rnb_ids))

    for geojson_geom in geojson_geometries:
        wheres.append(
            "ST_Intersects(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), c.shape)"
        )
        params.append(geojson_geom.json)

    wheres_str = " OR ".join(wheres)

    q = (
        "SELECT c.id, c.code_insee, c.name FROM batid_city as c "
        f"WHERE {wheres_str} "
        "ORDER BY c.code_insee"
    )

    cities = City.objects.raw(q, params)

    return [c for c in cities]
