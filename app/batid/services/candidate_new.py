from datetime import datetime, timezone

import nanoid
from django.db import transaction
from batid.services.bdg_status import BuildingStatus as BuildingStatusService
from batid.models import Candidate, Building, BuildingStatus


class Inspector:
    BATCH_SIZE = 1000

    MATCH_UPDATE_MIN_COVER_RATIO = 0.85
    MATCH_EXCLUDE_MAX_COVER_RATIO = 0.10

    def inspect(self):
        self.build_stamp()
        self.stamp_candidates()
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

    def inspect_candidate(self, c: Candidate):
        # Record the inspection datetime
        c.inspected_at = datetime.now(timezone.utc)

        # Light buildings do not match the RNB building definition
        if c.is_light == True:
            decide_refusal_is_light(c)
            return

        # Check the shape is big enough
        if

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

    def pick_one_candidate(self, id: int) -> Candidate:
        params = {
            "status": tuple(BuildingStatusService.REAL_BUILDINGS_STATUS),
            "inspect_stamp": self.stamp,
            "id": id,
        }

        q = (
            "SELECT c.id, ST_AsEWKB(c.shape) as shape, COALESCE(json_agg(json_build_object('id', b.id, 'shape', b.shape)) FILTER (WHERE b.id IS NOT NULL), '[]') as matches "
            f"FROM {Candidate._meta.db_table} c "
            f"LEFT JOIN {Building._meta.db_table} b on ST_Intersects(c.shape, b.shape) "
            f"LEFT JOIN {BuildingStatus._meta.db_table} bs on bs.building_id = b.id "
            "WHERE ((bs.type IN %(status)s AND bs.is_current) OR bs.id IS NULL) "
            "AND c.id = %(id)s "
            "GROUP BY c.id "
            "LIMIT 1"
        )

        qs = Candidate.objects.raw(q, params)
        return qs[0] if len(qs) > 0 else None

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


def decide_refusal_is_light(candidate: Candidate) -> Candidate:
    candidate.inspection_details = {"decision": "refusal", "reason": "is_light"}
    candidate.save()
