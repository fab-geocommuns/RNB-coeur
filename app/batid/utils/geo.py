from typing import List

from django.conf import settings
from django.contrib.gis.geos import GEOSGeometry
from django.contrib.gis.geos import MultiPolygon
from django.contrib.gis.geos import Polygon

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


def merge_contiguous_shapes(shapes: List[GEOSGeometry]):
    """
    Merge a list of contiguous GEOSGeometry shapes into a single shape.
    Supported GEOSGeometry types are Polygon and MultiPolygon.
    Function will raise if shapes given are not contiguous
    """
    if len(shapes) == 0:
        return None
    elif len(shapes) == 1:
        return shapes[0]
    else:
        if any(shape.geom_type not in ["Polygon", "MultiPolygon"] for shape in shapes):
            # one day we will also need to merge points with polygons, that will require additionnal work
            raise ImpossibleShapeMerge(
                "Seules les formes Polygon et MultiPolygon peuvent être fusionnées"
            )
        merged_shape = shapes[0]
        shapes = shapes[1:]

        while len(shapes) > 0:
            for i, shape in enumerate(shapes):
                if shape.intersects(merged_shape):
                    shape = shapes.pop(i)
                    merged_shape = merged_shape.union(shape)
                    break
            else:  # no break
                raise ImpossibleShapeMerge(
                    "Fusionner des bâtiments non contigus n'est pas possible"
                )
        # 7th decimal corresponds to approx 1cm
        # https://wiki.openstreetmap.org/wiki/Precision_of_coordinates

        # quadsegs is the number of points used to approximate a quarter of circle
        # we don't want the buffer to round corners, so we set quadsegs to 1 and join_style to 2
        # which means square join style.
        # that way a buffer around a rectangle is sill a rectangle.
        merged_shape = merged_shape.buffer_with_style(
            0.0000001, quadsegs=1, join_style=2
        ).buffer_with_style(-0.0000001, quadsegs=1, join_style=2)
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
        # web mercator reprojection
        # fine for a rough estimation of a building area (few % in France)
        # error is higher close to the poles
        geom_projected = g.transform(3857, clone=True)
        surface = geom_projected.area
        surface = round(surface)
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
