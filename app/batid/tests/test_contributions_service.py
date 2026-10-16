from batid.models import Contribution
from batid.services import contributions
from django.contrib.auth.models import User
from django.test import TestCase


class TestExportFormat(TestCase):
    def test_contributions_export(self):
        """
        Input: one contribution.
        Expected: one dict with the contribution text.
        """
        user = User.objects.create_user(username="exporter", email="e@example.com")
        Contribution.objects.create(rnb_id="BDG000000001", text="hello", user=user)

        rows = contributions.export_format()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["text"], "hello")
