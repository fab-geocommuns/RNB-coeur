import json
from django.contrib.gis.geos import GEOSGeometry


def feature_w_geom(feature: dict, srid=4326) -> dict:

    geom = GEOSGeometry(json.dumps(feature['geometry']))

    if geom.srid != srid:
        geom.transform(srid)

    feature['properties']['geom'] = geom
    feature['properties']['area'] = geom.area

    return feature