import nanoid
from django.db import transaction

from batid.models import Candidate


class Inspector:
    BATCH_SIZE = 1000

    MATCH_UPDATE_MIN_COVER_RATIO = 0.85
    MATCH_EXCLUDE_MAX_COVER_RATIO = 0.10


def inspect(self):
    self.buid_stamp()
    self.stamp_candidates()


def stamp_candidates(self) -> int:
    print("- reserve candidates")
    with transaction.atomic():
        # select_for_update() will lock the selected rows until the end of the transaction
        # avoid that another inspector selects the same candidates between the select and the update of this one
        candidates = (
            Candidate.objects.select_for_update()
            .filter(inspect_stamp__isnull=True)
            .order_by("?")[: self.BATCH_SIZE]
        )

        qs = Candidate.objects.filter(id__in=candidates).update(
            inspect_stamp=self.stamp
        )

        return qs.count()


def build_stamp(self):
    # The stamp must be lowercase since pg seems to lowercase it anyway
    # Postegresql uses the stamp to create a temporary table
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    self.stamp = nanoid.generate(size=12, alphabet=alphabet).lower()
    print(f"- stamp : {self.stamp}")
