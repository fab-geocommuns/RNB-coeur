import os
from datetime import datetime
from datetime import timezone
from typing import Literal

from celery import Signature
from django.conf import settings
from django.contrib.gis.geos import GEOSGeometry
from django.db import connection
from django.db import transaction
from psycopg2 import sql

from batid.models import Building
from batid.models import BuildingWithHistory
from batid.models import Candidate
from batid.services.bdg_status import BuildingStatus as BuildingStatusService
from batid.services.data_fix.fill_empty_event_origin import building_identicals


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

        try:
            with transaction.atomic():
                self.get_candidate()
                if isinstance(self.candidate, Candidate):
                    self.get_matching_bdgs()
                    self.inspect_candidate()
        except Exception as e:
            # We intercept the topology exception to avoid the task to crash
            # bug description : https://gis.stackexchange.com/questions/484691/topologyexception-side-location-conflict-while-intersects-on-valid-polygons
            if "TopologyException: side location conflict" in str(e):
                self.decide_refusal_topology_exception()
            else:
                raise e

    def reset(self):
        self.candidate = None
        self.matching_bdgs = []

    def get_candidate(self):
        q = sql.SQL(
            "SELECT id, ST_AsEWKB(shape) as shape, source, source_version, source_id, address_keys, is_light, inspected_at  FROM {candidate} WHERE inspected_at IS NULL ORDER BY inspected_at asc, random asc LIMIT 1 FOR UPDATE SKIP LOCKED"
        ).format(
            candidate=sql.Identifier(Candidate._meta.db_table),
        )
        qs = Candidate.objects.raw(q)
        self.candidate = qs[0] if len(qs) > 0 else None

    def get_matching_bdgs(self):

        q = sql.SQL(
            "SELECT id, ST_AsEWKB(shape) as shape "
            "FROM {building} "
            "WHERE ST_DWithin(shape::geography, ST_GeomFromText(%(c_shape)s)::geography, 3) "
            "AND status IN %(status)s "
            "AND is_active = true"
        ).format(
            building=sql.Identifier(Building._meta.db_table),
        )
        params = {
            "c_shape": f"{self.candidate.shape}",
            "status": tuple(BuildingStatusService.REAL_BUILDINGS_STATUS),
        }
        self.matching_bdgs = Building.objects.raw(q, params)

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
            if shape_area < settings.MIN_BUILDING_AREA:
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

    def decide_refusal_topology_exception(self):
        self.candidate.inspection_details = {
            "decision": "refusal",
            "reason": "topology_exception",
        }
        self.candidate.save()

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
        bdg = create_building_from_candidate(self.candidate)

        # Finally, we update the candidate
        self.candidate.inspection_details = {
            "decision": "creation",
            "rnb_id": bdg.rnb_id,
        }

        self.candidate.save()

    def decide_update(self):
        bdg = Building.objects.get(id=self.matching_bdgs[0].id)
        changes = self.calc_bdg_update(bdg)

        if changes:
            bdg.update(
                user=None,
                event_origin=changes.get("event_origin"),
                status=None,
                addresses_id=changes.get("addresses_id"),
                ext_ids=changes.get("ext_ids"),
                shape=changes.get("shape"),
            )
            self.candidate.inspection_details = {
                "decision": "update",
                "rnb_id": bdg.rnb_id,
            }
        else:
            self.candidate.inspection_details = {
                "decision": "refusal",
                "reason": "nothing_to_update",
            }
        self.candidate.save()

    def calc_bdg_update(self, bdg: Building) -> dict:
        changes = {}

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
            changes["ext_ids"] = Building.add_ext_id(
                bdg.ext_ids,
                self.candidate.source,
                self.candidate.source_version,
                self.candidate.source_id,
                self.candidate.created_at.isoformat(),
            )

        # ##
        # Prop : shape
        if (
            shape_family(self.candidate.shape) == "poly"
            and shape_family(bdg.shape) == "point"
        ):
            changes["shape"] = self.candidate.shape.clone()

        # ##############################
        # ADDRESSES
        # Handle change in addresses
        bdg_addresses = set(bdg.addresses_id or [])
        candidate_addresses = set(self.candidate.address_keys or [])

        if candidate_addresses - bdg_addresses:
            # update the addresses with the new ones
            changes["addresses_id"] = list(bdg_addresses | candidate_addresses)

        if changes:
            changes["event_origin"] = self.candidate.created_by

        # return an empty dict if nothing has changed
        # or a dict of changes
        return changes


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

    # We are sure the point is close to the polygon (the db query keeps buildings in a 3 meters radius)
    # So, it's always a match
    return "match"


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


def create_building_from_candidate(c: Candidate) -> Building:
    b = Building.create_new(
        # should we add a user here?
        user=None,
        event_origin=c.created_by,
        status="constructed",
        addresses_id=c.address_keys or [],
        shape=c.shape,
        ext_ids=[
            {
                "source": c.source,
                "source_version": c.source_version,
                "id": c.source_id,
                "created_at": c.created_at.isoformat(),
            }
        ],
    )

    return b


def create_inspection_tasks() -> list:

    tasks = []  # type: ignore[var-annotated]
    for _ in range(os.cpu_count()):  # type: ignore[arg-type]
        tasks.append(Signature("batid.tasks.inspect_candidates", immutable=True))

    return tasks


def display_report(since: datetime, requested_hecks: str = "all"):

    if not isinstance(since, datetime):
        raise ValueError("Since must be a datetime object")

    checks = _report_check_to_do(requested_hecks)

    if "count_decisions" in checks:

        print(">>> Count decisions")

        decisions = _report_count_decisions(since)
        for decision, count in decisions.items():
            print(f"Decision {decision} : {count:_}")

    if "count_refusals" in checks:

        print(">>> Count refusals per reason")

        refusals = _report_count_refusals(since)
        for reason, count in refusals.items():
            print(f"Reason {reason} : {count:_}")

    if "real_updates" in checks:

        print(">>> Check if updates are real updates")

        fake_updates = _report_list_fake_updates(since)

        if fake_updates:
            print(f"{len(fake_updates)} buildings have no real update")
            print(fake_updates)
        else:
            print(f"All updates are real updates")


def _report_check_to_do(requested_checks):

    available_checks = ["real_updates", "count_decisions", "count_refusals"]

    if requested_checks == "all":
        return available_checks

    return list(set(requested_checks.split(",")) & set(available_checks))


def _report_count_decisions(since: datetime) -> dict:

    q = """
        SELECT jsonb_extract_path_text(inspection_details, 'decision') AS reason, count(*)
        FROM batid_candidate
        WHERE inspected_at > %(since)s
        GROUP BY jsonb_extract_path_text(inspection_details, 'decision');
        """

    with connection.cursor() as cursor:
        cursor.execute(q, {"since": since})

        decisions = {}

        for row in cursor.fetchall():

            decisions[row[0]] = row[1]

        return decisions


def _report_count_refusals(since: datetime) -> dict:

    q = """
        SELECT jsonb_extract_path_text(inspection_details, 'reason') AS reason, count(*)
        FROM batid_candidate
        WHERE inspected_at > %(since)s and inspection_details @> '{"decision": "refusal"}'
        GROUP BY jsonb_extract_path_text(inspection_details, 'reason');
        """

    refusals = {}
    with connection.cursor() as cursor:
        cursor.execute(q, {"since": since})
        for row in cursor.fetchall():

            refusals[row[0]] = row[1]

    return refusals


def _report_list_fake_updates(since: datetime) -> list:
    """
    We check if each update made from candidate inspection
    has really updated at least one field in the building
    """

    q = """
            SELECT * FROM batid_candidate
            WHERE inspected_at >= %(since)s
            AND  inspection_details @> '{"decision": "update"}'
            limit 100 offset %(offset)s
            """

    params = {
        "since": since,
        "offset": 0,
    }
    batch_size = 1000
    checked_count = 0

    problems = []

    while True:

        candidates = Candidate.objects.raw(q, params)

        if not candidates:
            break

        # We check each updated building
        for candidate in candidates:

            rnb_id = candidate.inspection_details["rnb_id"]

            # todo : this query is ok with a rearely updated database.
            # We may upgrade it to get the right BuildingWithHistory based on a stronger critera
            # than "the last two history rows for this building"
            bdg_history = BuildingWithHistory.objects.filter(rnb_id=rnb_id).order_by(
                "-sys_period"
            )[:2]

            new = bdg_history[0]
            old = bdg_history[1]

            if building_identicals(new, old):
                problems.append(rnb_id)
                print(f"Building {rnb_id} has no real update")

            checked_count += 1

        params["offset"] += batch_size  # type: ignore[operator]

    return problems
