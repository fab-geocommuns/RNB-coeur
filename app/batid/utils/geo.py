from typing import List

from django.conf import settings
from django.contrib.gis.geos import GEOSGeometry
from django.contrib.gis.geos import MultiPolygon
from django.contrib.gis.geos import Polygon
from pyproj import Geod
from shapely import wkt

from batid.exceptions import BuildingTooLarge
from batid.exceptions import BuildingTooSmall
from batid.exceptions import ImpossibleShapeMerge
from batid.exceptions import InvalidWGS84Geometry


def fix_nested_shells(geom: GEOSGeometry) -> GEOSGeometry:
    if not isinstance(geom, MultiPolygon):
        raise ValueError(
            f"Nested shells errors can only be fixed on MultiPolygon object. {type(geom)} given"
        )

    if geom.valid:
        return geom

    # Convert a multipolygon with nested shells into a polygon with holes

    if "Nested shells" in geom.valid_reason:
        # get the biggest poly out of the list
        polys = list(geom)
        big_idx = None
        big_area = 0
        for idx, p in enumerate(polys):
            if p.num_interior_rings > 0:  # type: ignore[attr-defined]
                r = geom.buffer(0)
                return r

            if p.area > big_area:
                big_area = p.area  # type: ignore[assignment]
                big_idx = idx

        big_poly_ring = polys.pop(big_idx).coords[0]  # type: ignore[attr-defined,arg-type]
        small_polys_rings = [p.coords[0] for p in polys]  # type: ignore[attr-defined]

        geom = Polygon(big_poly_ring, *small_polys_rings)

    return geom


def merge_contiguous_shapes(shapes: List[GEOSGeometry]) -> GEOSGeometry:
    """
    Merge a list of contiguous GEOSGeometry shapes into a single shape.
    Supported GEOSGeometry types are Polygon and MultiPolygon.
    Function will raise if shapes given are not contiguous
    """
    # 7th decimal corresponds to approx 1cm
    # https://wiki.openstreetmap.org/wiki/Precision_of_coordinates
    buffer_size = 0.0000005
    if len(shapes) == 0:
        return None
    elif len(shapes) == 1:
        return shapes[0]
    else:
        buffered_shapes = [
            shape.buffer_with_style(buffer_size, quadsegs=1, join_style=2)
            for shape in shapes
        ]

        if any(shape.geom_type not in ["Polygon", "MultiPolygon"] for shape in shapes):
            # one day we will also need to merge points with polygons, that will require additionnal work
            raise ImpossibleShapeMerge(
                "Seules les formes Polygon et MultiPolygon peuvent être fusionnées"
            )
        merged_shape = buffered_shapes[0]
        buffered_shapes = buffered_shapes[1:]

        while len(buffered_shapes) > 0:
            for i, buffered_shape in enumerate(buffered_shapes):
                if buffered_shape.intersects(merged_shape):
                    buffered_shape = buffered_shapes.pop(i)
                    merged_shape = merged_shape.union(buffered_shape)
                    break
            else:  # no break
                raise ImpossibleShapeMerge(
                    "Fusionner des bâtiments non contigus n'est pas possible"
                )

        # quadsegs is the number of points used to approximate a quarter of circle
        # we don't want the buffer to round corners, so we set quadsegs to 1 and join_style to 2
        # which means square join style.
        # that way a buffer around a rectangle is sill a rectangle.
        merged_shape = merged_shape.buffer_with_style(
            -buffer_size, quadsegs=1, join_style=2
        )

        if not merged_shape.valid:
            merged_shape = merged_shape.make_valid()  # type: ignore[attr-defined]

        if not merged_shape.valid:
            raise ImpossibleShapeMerge(
                "La géometrie fusionnée serait invalide, la fusion est annulée."
            )

        return merged_shape


def assert_shape_is_valid(geom: GEOSGeometry):
    """Check if the provided WGS84 geometry is valid, and raises a InvalidWGS84Geometry exception if not."""
    if not geom.valid:
        raise InvalidWGS84Geometry()

    def check_simple_tuple(t):
        (lon, lat) = t
        if not (-180 <= lon <= 180):
            raise InvalidWGS84Geometry(
                f"La longitude est hors de la plage autorisée pour WGS84 (±180°) : {lon}"
            )
        if not (-90 <= lat <= 90):
            raise InvalidWGS84Geometry(
                f"La latitude est hors de la plage autorisée pour WGS84 (±90°) : {lat}"
            )

    def check_coords(g):
        coords = g.coords if hasattr(g, "coords") else g
        if (
            isinstance(coords, tuple)
            and len(coords) == 2
            and (type(coords[0]) == int or type(coords[0]) == float)
        ):
            check_simple_tuple(coords)
        else:
            for coord in coords:
                check_coords(coord)

    def check_area(g):

        if g.geom_type == "Point":
            return  # no area to check

        g.srid = 4326
        surface = compute_shape_area(g)

        if surface > settings.MAX_BUILDING_AREA:
            raise BuildingTooLarge(
                f"La surface du bâtiment ({surface}m²) est trop grande"
            )

        if surface < settings.MIN_BUILDING_AREA:
            raise BuildingTooSmall(
                f"La surface du bâtiment ({surface}m²) est trop petite"
            )

    check_coords(geom)
    check_area(geom)
    return True


def compute_shape_area(shape: GEOSGeometry) -> float:

    # source : https://chatgpt.com/share/6909dcdc-9878-8011-a7da-6dede9d747b7

    geod = Geod(ellps="WGS84")
    geom = wkt.loads(shape.wkt)
    area, _ = geod.geometry_area_perimeter(geom)

    return abs(area)
