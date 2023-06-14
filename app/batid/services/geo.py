from django.conf import settings
from shapely import wkb


# todo : inspector will be refactored. Once it is done, this function will be removed (will "migrate" from shapely to django geo lib)
def dbgeom_to_shapely(rowgeom):
    return wkb.loads(rowgeom, hex=True)


# todo : inspector will be refactored. Once it is done, this function will be removed (will "migrate" from shapely to django geo lib)
def shapely_to_dbgeom(shape):
    return wkb.dumps(shape, hex=True, srid=settings.DEFAULT_SRID)
