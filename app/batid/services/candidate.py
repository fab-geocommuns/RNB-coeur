import os
from datetime import datetime
from datetime import timezone
from celery import Signature
from typing import Literal

from django.conf import settings
from django.contrib.gis.geos import GEOSGeometry
from django.db import connection
from django.db import transaction

from batid.models import Building
from batid.models import Candidate
from batid.services.bdg_status import BuildingStatus as BuildingStatusService
from batid.services.rnb_id import generate_rnb_id


class Inspector:
    MATCH_BIG_COVER_RATIO = 0.85
    MATCH_SMALL_COVER_RATIO = 0.10

    def __int__(self):
        self.candidate = None
        self.matching_bdgs = []

    def inspect(self):
        while True:
            self.inspect_one()

            if self.candidate is None:
                return

    def inspect_one(self):
        self.reset()

        with transaction.atomic():
            self.get_candidate()
            if isinstance(self.candidate, Candidate):
                self.get_matching_bdgs()
                self.inspect_candidate()

    def reset(self):
        self.candidate = None
        self.matching_bdgs = []

    def get_candidate(self):
        q = f"SELECT id, ST_AsEWKB(shape) as shape, source, source_version, source_id, address_keys, is_light, inspected_at  FROM {Candidate._meta.db_table} WHERE inspected_at IS NULL ORDER BY inspected_at asc, random asc LIMIT 1 FOR UPDATE SKIP LOCKED"
        qs = Candidate.objects.raw(q)
        self.candidate = qs[0] if len(qs) > 0 else None

    def get_matching_bdgs(self):
        self.matching_bdgs = Building.objects.filter(
            shape__intersects=self.candidate.shape
        ).filter(status__in=BuildingStatusService.REAL_BUILDINGS_STATUS)

    def inspect_candidate(self):
        # Record the inspection datetime
        self.candidate.inspected_at = datetime.now(timezone.utc)

        # Light buildings do not match the RNB building definition
        if self.candidate.is_light == True:
            self.decide_refusal_is_light()
            return

        # Check the shape is big enough
        if shape_family(self.candidate.shape) == "poly":
            shape_area = compute_shape_area(self.candidate.shape)
            if shape_area < settings.MIN_BDG_AREA:
                self.decide_refusal_area_too_small(shape_area)
                return

        self.compare_matching_bdgs()

    def compare_matching_bdgs(self):
        kept_matches = []

        for bdg in self.matching_bdgs:
            shape_match_result = match_shapes(self.candidate.shape, bdg.shape)

            if shape_match_result == "match":
                kept_matches.append(bdg)
                continue

            if shape_match_result == "no_match":
                continue

            if shape_match_result == "conflict":
                self.decide_refusal_ambiguous_overlap(bdg.id)
                return

        self.matching_bdgs = kept_matches

        if len(self.matching_bdgs) == 0:
            self.decide_creation()

        if len(self.matching_bdgs) == 1:
            self.decide_update()

        if len(self.matching_bdgs) > 1:
            self.decide_refusal_too_many_geomatches()

    def decide_refusal_is_light(self):
        self.candidate.inspection_details = {
            "decision": "refusal",
            "reason": "is_light",
        }
        self.candidate.save()

    def decide_refusal_area_too_small(self, area: float):
        self.candidate.inspection_details = {
            "decision": "refusal",
            "reason": "area_too_small",
            "area": area,
        }
        self.candidate.save()

    def decide_refusal_ambiguous_overlap(self, conflict_with_bdg: int):
        self.candidate.inspection_details = {
            "decision": "refusal",
            "reason": "ambiguous_overlap",
            "conflict_with_bdg": conflict_with_bdg,
        }
        self.candidate.save()

    def decide_refusal_too_many_geomatches(self):
        self.candidate.inspection_details = {
            "decision": "refusal",
            "reason": "too_many_geomatches",
            "matches": [bdg.id for bdg in self.matching_bdgs],
        }
        self.candidate.save()

    def decide_creation(self):
        # We build the new building
        bdg = new_bdg_from_candidate(self.candidate)
        bdg.save()

        # Finally, we update the candidate
        self.candidate.inspection_details = {
            "decision": "creation",
            "rnb_id": bdg.rnb_id,
        }

        self.candidate.save()

    def decide_update(self):
        bdg = Building.objects.get(id=self.matching_bdgs[0].id)
        has_changed, bdg = self.calc_bdg_update(bdg)

        if has_changed:
            bdg.save()

        # Finally, we update the candidate
        self.candidate.inspection_details = {
            "decision": "update",
            "rnb_id": bdg.rnb_id,
        }
        self.candidate.save()

    def calc_bdg_update(self, bdg: Building):
        has_changed = False

        # ##############################
        # PROPERTIES
        # A place to verify properties changes
        # eg: ext_rnb_id, ext_bdnb_id, ...
        # If any property has changed, we will set has_changed_props to True

        # ##
        # Prop : ext_ids
        if not bdg.contains_ext_id(
            self.candidate.source,
            self.candidate.source_version,
            self.candidate.source_id,
        ):
            bdg.add_ext_id(
                self.candidate.source,
                self.candidate.source_version,
                self.candidate.source_id,
                self.candidate.created_at.isoformat(),
            )
            has_changed = True

        # ##
        # Prop : shape
        if (
            shape_family(self.candidate.shape) == "poly"
            and shape_family(bdg.shape) == "point"
        ):
            bdg.shape = self.candidate.shape.clone()
            has_changed = True

        # ##############################
        # ADDRESSES
        # Handle change in addresses
        def sort_handle_null(lst):
            return sorted(lst) if lst else []

        bdg_addresses = sort_handle_null(bdg.addresses_id)
        candidate_addresses = sort_handle_null(self.candidate.address_keys)
        if bdg_addresses != candidate_addresses:
            has_changed = True
            # concatenate the two lists and remove duplicates
            bdg.addresses_id = list(set(bdg_addresses + candidate_addresses))

        if has_changed:
            bdg.event_origin = self.candidate.created_by

        return has_changed, bdg


def add_addresses_to_building(bdg: Building, add_keys):
    bdg.addresses_id = add_keys
    bdg.save()


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

    # The building does not intersect enough with the candidate to be considered as a match
    if (
        a_cover_ratio < Inspector.MATCH_SMALL_COVER_RATIO
        and b_cover_ratio < Inspector.MATCH_SMALL_COVER_RATIO
    ):
        return "no_match"

    # The building intersects significantly with the candidate but not enough to be considered as a match
    if (
        a_cover_ratio < Inspector.MATCH_BIG_COVER_RATIO
        or b_cover_ratio < Inspector.MATCH_BIG_COVER_RATIO
    ):
        return "conflict"

    return "match"


def match_points(
    a: GEOSGeometry, b: GEOSGeometry
) -> Literal["match", "no_match", "conflict"]:
    if a.equals_exact(b, tolerance=0.0000001):
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


def new_bdg_from_candidate(c: Candidate) -> Building:
    point = c.shape if c.shape.geom_type == "Point" else c.shape.point_on_surface

    b = Building()
    b.rnb_id = generate_rnb_id()
    b.shape = c.shape
    b.point = point
    b.event_origin = c.created_by
    b.ext_ids = [
        {
            "source": c.source,
            "source_version": c.source_version,
            "id": c.source_id,
            "created_at": c.created_at.isoformat(),
        }
    ]
    b.addresses_id = c.address_keys

    return b


def create_inspection_tasks() -> list:

    tasks = []
    for _ in range(os.cpu_count()):
        tasks.append(Signature("batid.tasks.inspect_candidates", immutable=True))

    return tasks
