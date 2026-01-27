from typing import List

from django.conf import settings
from django.contrib.gis.geos import GeometryCollection
from django.contrib.gis.geos import GEOSGeometry
from django.contrib.gis.geos import MultiPolygon
from django.contrib.gis.geos import Polygon
from pyproj import Geod
from shapely import wkt
from shapely.ops import nearest_points

from batid.exceptions import BuildingCannotMove
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
    Merge a list of contiguous Polygon / MultiPolygon into a single Polygon or MultiPolygon.
    Raises ImpossibleShapeMerge if shapes are not contiguous or result is invalid.
    """

    if not shapes:
        raise ImpossibleShapeMerge("Au moins une géométrie doit être fournie")

    if any(s.geom_type not in ("Polygon", "MultiPolygon") for s in shapes):
        raise ImpossibleShapeMerge(
            "Seules les formes Polygon et MultiPolygon peuvent être fusionnées"
        )

    if len(shapes) == 1:
        return shapes[0]

    # ~ 5 cm
    # https://wiki.openstreetmap.org/wiki/Precision_of_coordinates
    buffer_size = 0.0000005

    # positive buffer to force contiguity
    buffered = [
        s.buffer_with_style(buffer_size, quadsegs=1, join_style=2) for s in shapes
    ]

    # union of all shapes in a single step
    merged = GeometryCollection(buffered).unary_union

    # if the shapes are not contiguous, the result will be a MultiPolygon
    # with more than one Polygon
    if isinstance(merged, MultiPolygon) and len(merged) > 1:
        raise ImpossibleShapeMerge(
            "Fusionner des bâtiments non contigus n'est pas possible"
        )

    # negative buffer to go back to original shape
    merged = merged.buffer_with_style(-buffer_size, quadsegs=1, join_style=2)

    # in case the result is not a valid geometry
    if not merged.valid:
        merged = merged.make_valid()  # type: ignore[attr-defined]

    if merged.geom_type == "GeometryCollection":
        merged = convert_geometry_collection(merged)

    if merged.geom_type not in ("Polygon", "MultiPolygon"):
        raise ImpossibleShapeMerge(
            f"Type de géométrie inattendu après fusion : {merged.geom_type}"
        )

    if not merged.valid:
        raise ImpossibleShapeMerge("La géométrie fusionnée est invalide")

    return merged


def convert_geometry_collection(geom: GEOSGeometry) -> GEOSGeometry:
    if geom.geom_type == "GeometryCollection":
        polygons = [
            g
            for g in geom  # type: ignore
            if g.geom_type in ("Polygon", "MultiPolygon") and not g.empty
        ]

        if len(polygons) == 1:
            return polygons[0]

    raise ImpossibleShapeMerge("La géométrie fusionnée est invalide")


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


def assert_new_shape_is_close_enough(
    old_geom: GEOSGeometry, new_geom: GEOSGeometry, max_dist: int = 20
) -> bool:
    # in case of intersection, we are fine
    if old_geom.intersects(new_geom):
        return True

    # otherwise, we check if the distance is less than max_dist
    # using a simplified criteria

    # Using shapely to calculate nearest points
    shapely_old_geom = wkt.loads(old_geom.wkt)
    shapely_new_geom = wkt.loads(new_geom.wkt)
    old_pos, new_pos = nearest_points(shapely_old_geom, shapely_new_geom)   

    geod = Geod(ellps="WGS84")

    _, _, dist_m = geod.inv(
        old_pos.x,
        old_pos.y,
        new_pos.x,
        new_pos.y,
    )

    if dist_m < max_dist:
        return True

    raise BuildingCannotMove()


def compute_shape_area(shape: GEOSGeometry) -> float:

    # source : https://chatgpt.com/share/6909dcdc-9878-8011-a7da-6dede9d747b7

    geod = Geod(ellps="WGS84")
    geom = wkt.loads(shape.wkt)
    area, _ = geod.geometry_area_perimeter(geom)

    return abs(area)


def drop_z(coords):
    if isinstance(coords[0], (float, int)):
        return coords[:2]  # (x, y, z) -> (x, y)
    return [drop_z(c) for c in coords]
