import time

from django.test import TestCase
from django.contrib.auth.models import User
from batid.models import Organization
from batid.tests.helpers import create_default_bdg
from batid.services.signal import create_signal


class TestSignalService(TestCase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = None
        self.building = None

    def setUp(self):
        self.user = User.objects.create_user(
            first_name="John", last_name="Doe", username="johndoe", email="john@doe.com"
        )
        org_1 = Organization.objects.create(
            name="Test Org", managed_cities=["12345", "67890"]
        )
        org_1.users.add(self.user)

        self.building = create_default_bdg()

    def test_create_signal(self):
        s = create_signal(
            type="test",
            building=self.building,
            origin="testOrigin",
            creator=self.user,
        )

        self.assertEqual(s.type, "test")
        self.assertEqual(s.building.rnb_id, self.building.rnb_id)
        self.assertEqual(s.origin, "testOrigin")
        self.assertEqual(s.creator_copy_id, self.user.pk)
        self.assertEqual(s.creator_copy_fname, self.user.first_name)
        self.assertEqual(s.creator_copy_lname, self.user.last_name)
        self.assertEqual(s.creator_org_copy_id, self.user.organizations.first().pk)
        self.assertEqual(s.creator_org_copy_name, self.user.organizations.first().name)

        return
