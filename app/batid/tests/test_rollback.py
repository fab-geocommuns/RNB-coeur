from django.contrib.auth.models import User
from django.contrib.gis.geos import GEOSGeometry
from django.test import override_settings
from django.test import TestCase

from batid.exceptions import RevertNotAllowed
from batid.models.building import Address
from batid.models.building import Building
from batid.models.building import EventType


class TestRollback(TestCase):
    @override_settings(MAX_BUILDING_AREA=float("inf"))
    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username="contributor",
            password="testpassword",
            email="contributor@example.test",
        )
        self.team_rnb = User.objects.create_user(username="Équipe RNB")
        self.shape_1 = GEOSGeometry("POLYGON((0 0, 0 1, 1 1, 1 0, 0 0))")
        self.building_1 = Building.create_new(
            user=self.user,
            event_origin={"source": "contribution", "contribution_id": 1},
            status="constructed",
            addresses_id=[],
            shape=self.shape_1,
            ext_ids=[],
        )
        self.building_2 = Building.create_new(
            user=self.user,
            event_origin={"source": "contribution", "contribution_id": 1},
            status="constructed",
            addresses_id=[],
            shape=GEOSGeometry("POLYGON((1 0, 1 1, 2 1, 2 0, 1 0))"),
            ext_ids=[],
        )
        self.address_1 = Address.objects.create(id="1")

    def test_revert_creation(self):
        creation_event_id = self.building_1.event_id
        Building.revert_event({"source": "rollback"}, creation_event_id)
        self.building_1.refresh_from_db()

        self.assertFalse(self.building_1.is_active)
        self.assertEqual(self.building_1.event_type, EventType.DEACTIVATION.value)
        self.assertEqual(self.building_1.revert_event_id, creation_event_id)
        self.assertNotEqual(self.building_1.event_id, creation_event_id)
        self.assertEqual(self.building_1.event_origin, {"source": "rollback"})
        self.assertEqual(self.building_1.status, "constructed")
        self.assertEqual(self.building_1.addresses_id, [])
        self.assertEqual(self.building_1.shape, self.shape_1)

    def test_revert_creation_impossible(self):
        creation_event_id = self.building_1.event_id
        self.building_1.update(
            self.user,
            {"source": "contribution"},
            status="demolished",
            addresses_id=None,
            ext_ids=None,
            shape=None,
        )
        self.building_1.refresh_from_db()

        with self.assertRaises(RevertNotAllowed) as e:
            Building.revert_event({"source": "rollback"}, creation_event_id)
            self.assertEqual(
                str(e.exception),
                "Impossible d'annuler la création du building, car il a été modifié entre temps.",
            )

        with self.assertRaises(RevertNotAllowed) as e:
            Building.revert_creation(
                self.team_rnb, {"source": "rollback"}, self.building_1.event_id
            )
            self.assertEqual(
                str(e.exception), "L'event_id n'est pas celui d'une création."
            )

    def test_revert_deactivation(self):
        creation_event_id = self.building_1.event_id

        with self.assertRaises(RevertNotAllowed):
            Building.revert_deactivation(
                self.team_rnb, {"source": "rollback"}, creation_event_id
            )

        self.building_1.deactivate(self.user, {"source": "contribution"})
        self.building_1.refresh_from_db()
        deactivation_event_id = self.building_1.event_id

        Building.revert_event({"source": "rollback"}, deactivation_event_id)
        self.building_1.refresh_from_db()

        self.assertTrue(self.building_1.is_active)
        self.assertEqual(self.building_1.event_type, EventType.REACTIVATION.value)
        self.assertEqual(self.building_1.revert_event_id, deactivation_event_id)
        self.assertNotEqual(self.building_1.event_id, deactivation_event_id)
        self.assertEqual(self.building_1.event_origin, {"source": "rollback"})
        self.assertEqual(self.building_1.status, "constructed")
        self.assertEqual(self.building_1.addresses_id, [])
        self.assertEqual(self.building_1.shape, self.shape_1)

    def test_revert_deactivation_impossible(self):
        self.building_1.deactivate(self.user, {"source": "contribution"})
        deactivation_event_id = self.building_1.event_id
        self.building_1.reactivate(self.user, {"source": "contribution"})
        self.building_1.update(
            self.user,
            {"source": "contribution"},
            status="demolished",
            addresses_id=None,
            ext_ids=None,
            shape=None,
        )
        self.building_1.refresh_from_db()

        with self.assertRaises(RevertNotAllowed) as e:
            Building.revert_event({"source": "rollback"}, deactivation_event_id)
            self.assertEqual(
                str(e.exception),
                "Impossible d'annuler la désactivation du building, car il a été modifié entre temps.",
            )

        with self.assertRaises(RevertNotAllowed) as e:
            Building.revert_creation(
                self.team_rnb, {"source": "rollback"}, self.building_1.event_id
            )
            self.assertEqual(
                str(e.exception), "L'event_id n'est pas celui d'une désactivation."
            )

    def test_revert_update(self):
        self.building_1.update(
            self.user,
            {"source": "contribution"},
            status="demolished",
            addresses_id=[self.address_1.id],
            ext_ids=[{"source": "bdtopo", "id": "XXX"}],
            shape=GEOSGeometry("POINT(0 0)"),
        )
        self.building_1.refresh_from_db()
        self.building_1.update(
            self.user,
            {"source": "contribution"},
            status="notUsable",
            addresses_id=[],
            ext_ids=[{"source": "bdtopo", "id": "YYY"}],
            shape=GEOSGeometry("POINT(1 1)"),
        )
        self.building_1.refresh_from_db()
        update_event_id = self.building_1.event_id

        Building.revert_event({"source": "rollback"}, update_event_id)
        self.building_1.refresh_from_db()

        self.assertEqual(self.building_1.event_type, EventType.REVERT_UPDATE.value)
        self.assertEqual(self.building_1.revert_event_id, update_event_id)
        self.assertNotEqual(self.building_1.event_id, update_event_id)
        self.assertEqual(self.building_1.event_origin, {"source": "rollback"})
        self.assertEqual(self.building_1.status, "demolished")
        self.assertEqual(self.building_1.addresses_id, [self.address_1.id])
        self.assertEqual(self.building_1.shape.wkt, GEOSGeometry("POINT(0 0)").wkt)

    def test_revert_update_impossible(self):
        self.building_1.update(
            self.user,
            {"source": "contribution"},
            status="demolished",
            addresses_id=None,
            ext_ids=None,
            shape=None,
        )
        update_event_id = self.building_1.event_id

        self.building_1.update(
            self.user,
            {"source": "contribution"},
            status="notUsable",
            addresses_id=None,
            ext_ids=None,
            shape=None,
        )
        self.building_1.refresh_from_db()

        with self.assertRaises(RevertNotAllowed) as e:
            Building.revert_event({"source": "rollback"}, update_event_id)
            self.assertEqual(
                str(e.exception),
                "Impossible d'annuler la mise à jour du building, car il a été modifié entre temps.",
            )

        with self.assertRaises(RevertNotAllowed) as e:
            Building.revert_creation(
                self.team_rnb, {"source": "rollback"}, self.building_1.event_id
            )
            self.assertEqual(
                str(e.exception), "L'event_id n'est pas celui d'une mise à jour."
            )
