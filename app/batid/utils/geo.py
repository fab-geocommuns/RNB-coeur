from django.contrib.gis.geos import GEOSGeometry
from django.contrib.gis.geos import MultiPolygon
from django.contrib.gis.geos import Polygon


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
            if p.num_interior_rings > 0:
                r = geom.buffer(0)
                return r

                # raise ValueError(
                #     "We have a sub-polygon with holes, we can't rebuild a clean polygon."
                # )

            if p.area > big_area:
                big_area = p.area
                big_idx = idx

        big_poly_ring = polys.pop(big_idx).coords[0]
        small_polys_rings = [p.coords[0] for p in polys]

        geom = Polygon(big_poly_ring, *small_polys_rings)

    return geom


def merge_contiguous_shapes(shapes: list):
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
            raise Exception("Only Polygon and MultiPolygon shapes can be merged")
        merged_shape = shapes[0]
        shapes = shapes[1:]

        while len(shapes) > 0:
            for i, shape in enumerate(shapes):
                if shape.intersects(merged_shape):
                    shape = shapes.pop(i)
                    merged_shape = merged_shape.union(shape)
                    break
            else:  # no break
                raise Exception("we don't want to merge non-contiguous shapes")
        return merged_shape
