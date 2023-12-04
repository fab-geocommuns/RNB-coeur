import json
from datetime import datetime, timezone
from typing import Literal

import nanoid
from django.conf import settings
from django.contrib.gis.geos import GEOSGeometry, Point
from django.db import transaction, connection
from shapely.geometry import shape

from batid.services.bdg_status import BuildingStatus as BuildingStatusService
from batid.models import Candidate, Building, BuildingStatus, Address
from batid.services.rnb_id import generate_rnb_id


class Inspector:
    BATCH_SIZE = 1000

    MATCH_UPDATE_MIN_COVER_RATIO = 0.85
    MATCH_EXCLUDE_MAX_COVER_RATIO = 0.10

    def __int__(self):
        self.stamp = None
        self.candidates = []
        self.addresses = {}

    def inspect(self):
        self.build_stamp()
        self.stamp_candidates()
        self.get_candidates()
        self.get_addresses()
        self.inspect_candidates()
        self.report()

    def inspect_candidates(self):
        ids = Candidate.objects.filter(
            inspect_stamp=self.stamp, inspected_at__isnull=True
        ).values_list("id", flat=True)

        for id in ids:
            print(f"Inspecting candidate {id}")
            with transaction.atomic():
                c = self.pick_one_candidate(id)

                # We have a candidate to inspect
                try:
                    self.inspect_candidate(c)
                except Exception as e:
                    # We had an error while inspecting the candidate
                    # The transaction is rolled back : https://docs.djangoproject.com/en/4.2/topics/db/transactions/#django.db.transaction.atomic
                    # We reset the candidate inspection to make it available again
                    self.handle_error_on_candidate(c)

            # Here the transaction is committed and we know it went ok
            # We can update BuildingImport data
            self.add_to_report(c)

    def get_candidates(self):
        params = {
            "status": tuple(BuildingStatusService.REAL_BUILDINGS_STATUS),
            "inspect_stamp": self.stamp,
        }

        q = (
            "SELECT c.id, ST_AsEWKB(c.shape) as shape, COALESCE(json_agg(json_build_object('id', b.id, 'shape', b.shape)) FILTER (WHERE b.id IS NOT NULL), '[]') as matches, c.address_keys "
            f"FROM {Candidate._meta.db_table} c "
            f"LEFT JOIN {Building._meta.db_table} b on ST_Intersects(c.shape, b.shape) "
            f"LEFT JOIN {BuildingStatus._meta.db_table} bs on bs.building_id = b.id "
            "WHERE ((bs.type IN %(status)s AND bs.is_current) OR bs.id IS NULL) "
            "AND c.inspected_at IS NULL AND c.inspect_stamp = %(inspect_stamp)s "
            "GROUP BY c.id "
        )

        self.candidates = Candidate.objects.raw(q, params)

    def get_addresses(self):
        address_keys = set()

        for c in self.candidates:
            for k in c.address_keys:
                address_keys.add(k)

        addresses = Address.objects.filter(id__in=address_keys)

        for a in addresses:
            self.addresses[a.id] = a

    def inspect_candidate(self, c: Candidate):
        # Record the inspection datetime
        c.inspected_at = datetime.now(timezone.utc)

        # Light buildings do not match the RNB building definition
        if c.is_light == True:
            decide_refusal_is_light(c)
            return

        # Check the shape is big enough
        if shape_family(c.shape) == "poly":
            shape_area = compute_shape_area(c.shape)
            if shape_area < settings.MIN_BDG_AREA:
                decide_refusal_area_too_small(c, shape_area)
                return

        self.inspect_candidate_matches(c)

    def inspect_candidate_matches(self, c: Candidate):
        kept_matches = []
        for match in c.matches:
            b_shape = GEOSGeometry(json.dumps(match["shape"]))

            shape_match_result = match_shapes(c.shape, b_shape)

            if shape_match_result == "match":
                kept_matches.append(match)
                continue

            if shape_match_result == "no_match":
                continue

            if shape_match_result == "conflict":
                decide_refusal_ambiguous_overlap(c, match["id"])
                return

        c.matches = kept_matches

        if len(c.matches) == 0:
            b = self.create_bdg_from_candidate(c)
            decide_creation(c, b)

        if len(c.matches) == 1:
            b = self.update_bdg_from_candidate(c)
            decide_update(c, b)

        if len(c.matches) > 1:
            decide_refusal_toomany_geomatches(c)

    def report(self):
        # todo : we can use the report to update BuildingImport data
        pass

    def add_to_report(self, c: Candidate):
        # Todo: count all add/update/delete for all BuildingImports
        pass

    def handle_error_on_candidate(self, c: Candidate):
        print(f"Error on candidate {c.id}")
        self.reset_candidate_inspection(c)

    @staticmethod
    def reset_candidate_inspection(c: Candidate):
        c.inspection_details = None
        c.inspected_at = None
        c.inspect_stamp = None
        c.save()

    def stamp_candidates(self) -> int:
        print("- reserve candidates")
        with transaction.atomic():
            # select_for_update() will lock the selected rows until the end of the transaction
            # avoid that another inspector selects the same candidates between the select and the update of this one
            candidates = (
                Candidate.objects.select_for_update(skip_locked=True)
                .filter(inspect_stamp__isnull=True)
                .order_by("?")[: self.BATCH_SIZE]
            )

            Candidate.objects.filter(id__in=candidates).update(inspect_stamp=self.stamp)

    def build_stamp(self):
        # The stamp must be lowercase since pg seems to lowercase it anyway
        # Postegresql uses the stamp to create a temporary table
        alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZ"
        self.stamp = nanoid.generate(size=12, alphabet=alphabet).lower()
        print(f"- stamp : {self.stamp}")


def match_shapes(
    a: GEOSGeometry, b: GEOSGeometry
) -> Literal["match", "no_match", "conflict"]:
    families = (shape_family(a), shape_family(b))

    if families == ("poly", "poly"):
        return match_polygons(a, b)

    if families == ("point", "point"):
        return match_points(a, b)

    if families == ("point", "poly") or families == ("poly", "point"):
        return match_point_poly(a, b)

    raise Exception(f"Unknown matching shape families case: {families}")


def match_polygons(
    a: GEOSGeometry, b: GEOSGeometry
) -> Literal["match", "no_match", "conflict"]:
    intersection = a.intersection(b)

    a_cover_ratio = intersection.area / a.area
    b_cover_ratio = intersection.area / b.area

    print(f"cover ratio : {a_cover_ratio} {b_cover_ratio}")

    # The building does not intersect enough with the candidate to be considered as a match
    if (
        a_cover_ratio < Inspector.MATCH_EXCLUDE_MAX_COVER_RATIO
        and b_cover_ratio < Inspector.MATCH_EXCLUDE_MAX_COVER_RATIO
    ):
        return "no_match"

    # The building intersects significantly with the candidate but not enough to be considered as a match
    if (
        a_cover_ratio < Inspector.MATCH_UPDATE_MIN_COVER_RATIO
        or b_cover_ratio < Inspector.MATCH_UPDATE_MIN_COVER_RATIO
    ):
        return "conflict"

    return "match"


def match_points(a: Point, b: Point) -> Literal["match", "no_match", "conflict"]:
    if a.equals_exact(b, tolerance=0.00000000000001):
        return "match"

    return "no_match"


def match_point_poly(
    a: GEOSGeometry, b: GEOSGeometry
) -> Literal["match", "no_match", "conflict"]:
    # NB : this intersection verification is already done in the sql query BUT we want to be sure this matching condition is always verified even the SQL query is modified
    if a.intersects(b):
        return "match"

    return "no_match"


def shape_family(shape: GEOSGeometry):
    if shape.geom_type == "MultiPolygon":
        return "poly"

    if shape.geom_type == "Polygon":
        return "poly"

    if shape.geom_type == "Point":
        return "point"

    raise Exception(f"We do not know the family this shape type: {shape.geom_type}")


def compute_shape_area(shape):
    with connection.cursor() as cursor:
        cursor.execute("select ST_AREA(%s, true)", [shape.wkt])
        row = cursor.fetchone()

    return row[0]


def decide_refusal_is_light(candidate: Candidate):
    candidate.inspection_details = {"decision": "refusal", "reason": "is_light"}
    candidate.save()


def decide_refusal_area_too_small(candidate: Candidate, area: float):
    candidate.inspection_details = {
        "decision": "refusal",
        "reason": "area_too_small",
        "area": area,
    }
    candidate.save()


def decide_refusal_ambiguous_overlap(candidate: Candidate, conflict_with_bdg: int):
    candidate.inspection_details = {
        "decision": "refusal",
        "reason": "ambiguous_overlap",
        "conflict_with_bdg": conflict_with_bdg,
    }
    candidate.save()


def decide_refusal_toomany_geomatches(candidate: Candidate) -> Candidate:
    candidate.inspection_details = {
        "decision": "refusal",
        "reason": "toomany_geomatches",
        "matches": [m["id"] for m in candidate.matches],
    }
    candidate.save()


def decide_update(candidate: Candidate):
    pass


def decide_creation(candidate: Candidate):
    b = candidate_to_bdg(candidate)

    pass


def candidate_to_bdg(c: Candidate) -> Building:
    point = c.shape if c.shape.geom_type == "Point" else c.shape.point_on_surface

    b = Building()
    b.rnb_id = generate_rnb_id()
    b.shape = c.shape
    b.point = point
    b.last_updated_by = c.created_by
    b.ext_ids = {
        "source": c.source,
        "source_version": c.source_version,
        "id": c.source_id,
        "created_at": c.created_at.isoformat(),
    }

    return b
