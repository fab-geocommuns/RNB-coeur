from django.conf import settings
from shapely import wkb


def dbgeom_to_shapely(rowgeom):
    return wkb.loads(rowgeom, hex=True)


def shapely_to_dbgeom(shape):
    return wkb.dumps(shape, hex=True, srid=settings.DEFAULT_SRID)
