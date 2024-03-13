from django.contrib.auth.models import User
from django.test import TestCase

from batid.models import Organization
from batid.services.signal import create_async_signal
from batid.tests.helpers import create_default_bdg
from batid.tests.helpers import create_grenoble


class TestSignal(TestCase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = None
        self.building = None
        self.city = None

    def setUp(self):
        self.user = User.objects.create_user(
            first_name="John", last_name="Doe", username="johndoe", email="john@doe.com"
        )
        org_1 = Organization.objects.create(
            name="Test Org", managed_cities=["12345", "67890"]
        )
        org_1.users.add(self.user)

        self.building = create_default_bdg()

        self.city = create_grenoble()

    def test_create_signal(self):
        s = create_async_signal(
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

    # def test_ads_signal_handle(self):
    #     # Create an ADS. It should create a signal linked to it.
    #     ads = ADS.objects.create(
    #         city=self.city, file_number="GOGO", decided_at="2020-01-01"
    #     )
    #     BuildingADS.objects.create(building=self.building, ads=ads, operation="build")

    #     signals = AsyncSignal.objects.filter(
    #         building=self.building, type="calcStatusFromADS"
    #     )

    #     # We verify the signal is created
    #     self.assertEqual(len(signals), 1)
    #     s = signals.first()
    #     self.assertEqual(s.type, "calcStatusFromADS")

    #     # Then we verify it is correctly dispatched
    #     sh = AsyncSignalDispatcher()
    #     sh.dispatch(s)

    #     s.refresh_from_db()

    #     # After the dispatch, the building inside the signal must have a "constructionProject" status
    #     self.assertEqual(s.building.status, "constructionProject")

    #     # We also verify the signal has been handled correctly
    #     self.assertIsNotNone(s.handled_at)

    #     expected_result = {
    #         "handler": "CalcBdgStatusFromADSHandler",
    #         "action": "create",
    #         "target": model_to_code(self.building.status),
    #     }
    #     ads_result = next(
    #         r for r in s.handle_result if r["handler"] == "CalcBdgStatusFromADSHandler"
    #     )

    #     self.assertDictEqual(ads_result, expected_result)

    # def test_ads_multiple_signal_handle(self):
    #     # We want to verify that if we create two similar signals, only one status is created

    #     ads = ADS.objects.create(
    #         city=self.city, file_number="MULTI", decided_at="2020-01-01"
    #     )
    #     op = BuildingADS.objects.create(
    #         building=self.building, ads=ads, operation="build"
    #     )

    #     # We modify once ...
    #     op.operation = "demolish"
    #     op.save()
    #     # ... and come back to "build" to create a second similar signal
    #     op.operation = "build"
    #     op.save()

    #     signals = AsyncSignal.objects.filter(
    #         building=self.building, type="calcStatusFromADS"
    #     )
    #     self.assertEqual(len(signals), 3)

    #     # We have to signals (they must be quite identical)
    #     # We dispatch them and verify there is only on statuts attached to the building
    #     sh = AsyncSignalDispatcher()
    #     for s in signals:
    #         sh.dispatch(s)

    #     self.assertEqual(len(self.building.status.all()), 1)
