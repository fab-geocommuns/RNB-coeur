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
            "Impossible to revert the building creation, because it has been modified.",
        )

        with self.assertRaises(RevertNotAllowed) as e:
            Building.revert_creation(
                self.team_rnb, {"source": "rollback"}, self.building_1.event_id
            )

        self.assertEqual(
            str(e.exception), "The event_id does not correspond to a creation."
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
            "Impossible to revert the building deactivation, because it has been modified.",
        )

        with self.assertRaises(RevertNotAllowed) as e:
            Building.revert_deactivation(
                self.team_rnb, {"source": "rollback"}, self.building_1.event_id
            )
        self.assertEqual(
            str(e.exception), "The event_id does not correspond to a deactivation."
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

        self.building_1.deactivate(self.user, {"source": "contribution"})
        self.building_1.refresh_from_db()
        deactivation_event_id = self.building_1.event_id

        with self.assertRaises(RevertNotAllowed) as e:
            Building.revert_event({"source": "rollback"}, update_event_id)
        self.assertEqual(
            str(e.exception),
            "Impossible to revert the building update, because it has been modified.",
        )

        with self.assertRaises(RevertNotAllowed) as e:
            Building.revert_update(
                self.team_rnb, {"source": "rollback"}, deactivation_event_id
            )
        self.assertEqual(
            str(e.exception), "The event_id does not correspond to an update."
        )

    @override_settings(MAX_BUILDING_AREA=float("inf"))
    def test_revert_split(self):
        created_buildings = self.building_1.split(
            [
                {
                    "status": "constructed",
                    "addresses_cle_interop": [],
                    "shape": "POLYGON((0 0, 0 2, 2 2, 2 0, 0 0))",
                },
                {
                    "status": "constructionProject",
                    "addresses_cle_interop": [self.address_1.id],
                    "shape": "POLYGON((0 0, 0 1, 1 1, 1 0, 0 0))",
                },
            ],
            self.user,
            {"source": "contribution"},
        )

        self.building_1.refresh_from_db()
        split_event_id = self.building_1.event_id

        Building.revert_event({"source": "rollback"}, split_event_id)
        self.building_1.refresh_from_db()
        new_event_id = self.building_1.event_id

        self.assertEqual(self.building_1.event_type, EventType.REVERT_SPLIT.value)
        self.assertEqual(self.building_1.revert_event_id, split_event_id)
        self.assertNotEqual(new_event_id, split_event_id)
        self.assertEqual(self.building_1.event_origin, {"source": "rollback"})
        self.assertEqual(self.building_1.status, "constructed")
        self.assertEqual(self.building_1.addresses_id, [])
        self.assertEqual(
            self.building_1.shape.wkt,
            GEOSGeometry("POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))").wkt,
        )

        child_1 = created_buildings[0]
        child_1.refresh_from_db()

        self.assertFalse(child_1.is_active)
        self.assertEqual(self.building_1.event_type, EventType.REVERT_SPLIT.value)
        self.assertEqual(child_1.event_id, new_event_id)

        child_2 = created_buildings[0]
        child_2.refresh_from_db()

        self.assertFalse(child_2.is_active)
        self.assertEqual(self.building_1.event_type, EventType.REVERT_SPLIT.value)
        self.assertEqual(child_2.event_id, new_event_id)

    @override_settings(MAX_BUILDING_AREA=float("inf"))
    def test_revert_split_impossible(self):
        created_buildings = self.building_1.split(
            [
                {
                    "status": "constructed",
                    "addresses_cle_interop": [],
                    "shape": "POLYGON((0 0, 0 2, 2 2, 2 0, 0 0))",
                },
                {
                    "status": "constructionProject",
                    "addresses_cle_interop": [self.address_1.id],
                    "shape": "POLYGON((0 0, 0 1, 1 1, 1 0, 0 0))",
                },
            ],
            self.user,
            {"source": "contribution"},
        )
        child_1 = created_buildings[0]
        split_event_id = child_1.event_id

        # a child is updated, reverting the split won't be possible
        child_1.update(
            self.user,
            {"source": "contribution"},
            status="notUsable",
            addresses_id=None,
            ext_ids=None,
            shape=None,
        )

        with self.assertRaises(RevertNotAllowed) as e:
            Building.revert_event({"source": "rollback"}, split_event_id)

        self.assertEqual(
            str(e.exception),
            "Impossible to revert the building split, because it has been modified.",
        )

    @override_settings(MAX_BUILDING_AREA=float("inf"))
    def test_revert_merge(self):
        building = Building.merge(
            [self.building_1, self.building_2],
            self.user,
            {"source": "contribution"},
            status="constructed",
            addresses_id=[self.address_1.id],
        )
        merge_event_id = building.event_id

        Building.revert_event({"source": "rollback"}, merge_event_id)
        building.refresh_from_db()
        new_event_id = building.event_id

        self.assertEqual(building.event_type, EventType.REVERT_MERGE.value)
        self.assertEqual(building.revert_event_id, merge_event_id)
        self.assertNotEqual(new_event_id, merge_event_id)
        self.assertEqual(building.event_origin, {"source": "rollback"})
        self.assertEqual(building.status, "constructed")
        self.assertEqual(building.addresses_id, [self.address_1.id])
        self.assertAlmostEqual(building.shape.area, 2, delta=0.01)

        parent_1 = self.building_1
        parent_1.refresh_from_db()

        self.assertTrue(parent_1.is_active)
        self.assertEqual(self.building_1.event_type, EventType.REVERT_MERGE.value)
        self.assertEqual(parent_1.event_id, new_event_id)

        parent_2 = self.building_2
        parent_2.refresh_from_db()

        self.assertTrue(parent_2.is_active)
        self.assertEqual(self.building_1.event_type, EventType.REVERT_MERGE.value)
        self.assertEqual(parent_2.event_id, new_event_id)

    @override_settings(MAX_BUILDING_AREA=float("inf"))
    def test_revert_merge_impossible(self):
        building = Building.merge(
            [self.building_1, self.building_2],
            self.user,
            {"source": "contribution"},
            status="constructed",
            addresses_id=[self.address_1.id],
        )
        merge_event_id = building.event_id
        building.update(
            self.user,
            event_origin={"source": "contribution"},
            status="demolished",
            addresses_id=None,
        )
        building.refresh_from_db()

        with self.assertRaises(RevertNotAllowed) as e:
            Building.revert_event({"source": "rollback"}, merge_event_id)

        self.assertEqual(
            str(e.exception),
            "Impossible to revert the building merge, because it has been modified.",
        )
