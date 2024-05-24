from django.db.utils import IntegrityError
from django.test import TransactionTestCase

from batid.models import Candidate


class CandidateTestCase(TransactionTestCase):
    def test_db_constraints(self):
        # insert valid candidates
        Candidate.objects.create(source="bdnb")
        Candidate.objects.create(
            source="bdnb",
            inspection_details={"decision": "refusal", "reason": "area_too_small"},
        )
        Candidate.objects.create(
            source="bdnb", inspection_details={"decision": "update"}
        )
        Candidate.objects.create(
            source="bdnb", inspection_details={"decision": "creation"}
        )

        # candidates not respecting the constraints -> boom
        self.assertRaises(
            IntegrityError,
            Candidate.objects.create,
            source="bdnb",
            inspection_details={"decision": "merge"},
        )
        self.assertRaises(
            IntegrityError,
            Candidate.objects.create,
            source="bdnb",
            inspection_details={"Decision": "creation"},
        )
