from django.contrib.auth.models import User
from django.contrib.gis.geos import GEOSGeometry
from django.test import override_settings
from django.test import TransactionTestCase

from batid.exceptions import RevertNotAllowed
from batid.models.building import Address
from batid.models.building import Building
from batid.models.building import BuildingWithHistory
from batid.models.building import EventType
from batid.services.rollback import rollback
from batid.services.rollback import rollback_dry_run


class TestUnitaryRollback(TransactionTestCase):
    @override_settings(MAX_BUILDING_AREA=float("inf"))
    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username="contributor",
            password="testpassword",
            email="contributor@example.test",
        )
        self.other_user = User.objects.create_user(
            username="contributor_2",
            password="testpassword",
            email="contributor_2@example.test",
        )
        self.team_rnb = User.objects.create_user(username="RNB")
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
        self.assertEqual(self.building_1.event_type, EventType.REVERT_CREATION.value)
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
            self.other_user,
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


class TestGlobalRollback(TransactionTestCase):
    @override_settings(MAX_BUILDING_AREA=float("inf"))
    def setUp(self):
        self.user = User.objects.create_user(
            username="contributor",
            password="testpassword",
            email="contributor@example.test",
        )
        self.other_user = User.objects.create_user(
            username="contributor_2",
            password="testpassword",
            email="contributor_2@example.test",
        )
        self.team_rnb = User.objects.create_user(username="RNB")

        self.shape_1 = GEOSGeometry("POLYGON((0 0, 0 1, 1 1, 1 0, 0 0))")

        self.building_old = Building.create_new(
            user=self.user,
            event_origin={"source": "contribution", "contribution_id": 1},
            status="constructed",
            addresses_id=[],
            shape=self.shape_1,
            ext_ids=[],
        )
        self.building_1 = Building.create_new(
            user=self.user,
            event_origin={"source": "contribution", "contribution_id": 2},
            status="constructed",
            addresses_id=[],
            shape=self.shape_1,
            ext_ids=[],
        )
        self.building_2 = Building.create_new(
            user=self.user,
            event_origin={"source": "contribution", "contribution_id": 3},
            status="constructed",
            addresses_id=[],
            shape=GEOSGeometry("POLYGON((1 0, 1 1, 2 1, 2 0, 1 0))"),
            ext_ids=[],
        )
        self.building_other_user = Building.create_new(
            user=self.other_user,
            event_origin={"source": "contribution", "contribution_id": 4},
            status="constructed",
            addresses_id=[],
            shape=self.shape_1,
            ext_ids=[],
        )
        self.address_1 = Address.objects.create(id="1")

    def test_global_rollback(self):
        self.building_1.refresh_from_db()
        start_time = self.building_1.sys_period.lower
        end_time = None

        results = rollback_dry_run(self.user, start_time, end_time)

        self.assertEqual(results["user"], self.user.username)
        self.assertEqual(results["events_found_n"], 2)
        self.assertEqual(results["start_time"], start_time)
        self.assertEqual(results["end_time"], end_time)
        self.assertEqual(results["events_revertable_n"], 2)
        self.assertEqual(results["events_not_revertable_n"], 0)
        self.assertEqual(
            set(results["events_revertable"]),
            set({self.building_1.event_id, self.building_2.event_id}),
        )

        # Rollback for real
        results = rollback(self.user, start_time, end_time)

        self.assertEqual(results["user"], self.user.username)
        self.assertEqual(results["events_found_n"], 2)
        self.assertEqual(results["start_time"], start_time)
        self.assertEqual(results["end_time"], end_time)
        self.assertEqual(results["events_reverted_n"], 2)
        self.assertEqual(results["events_not_revertable_n"], 0)
        self.assertEqual(
            set(results["events_reverted"]),
            set({self.building_1.event_id, self.building_2.event_id}),
        )
        building_1_creation_event_id = self.building_1.event_id
        building_2_creation_event_id = self.building_2.event_id

        # check the buildings creation have been rolled back
        self.building_1.refresh_from_db()
        self.assertFalse(self.building_1.is_active)
        self.assertEqual(self.building_1.event_type, EventType.REVERT_CREATION.value)
        self.assertEqual(self.building_1.revert_event_id, building_1_creation_event_id)

        self.building_2.refresh_from_db()
        self.assertFalse(self.building_2.is_active)
        self.assertEqual(self.building_2.event_type, EventType.REVERT_CREATION.value)
        self.assertEqual(self.building_2.revert_event_id, building_2_creation_event_id)

    def test_global_rollback_2(self):
        """Here a user creates 2 buildings and then update one of the created building. An other user updates the other building.
        only the first building creation + update is revertable.
        The second building creation is locked by the update made by other_user
        """
        self.building_1.refresh_from_db()
        start_time = self.building_1.sys_period.lower
        end_time = None
        building_1_creation_event_id = self.building_1.event_id
        building_2_creation_event_id = self.building_2.event_id

        # the building is updated by the same user, the rollback should be possible
        self.building_1.update(
            self.user,
            {"source": "contribution"},
            status="demolished",
            addresses_id=None,
        )
        self.building_1.refresh_from_db()
        building_1_update_event_id = self.building_1.event_id
        # the building is updated by another user, the rollback should not be possible
        self.building_2.update(
            self.other_user,
            {"source": "contribution"},
            status="demolished",
            addresses_id=None,
        )

        results = rollback_dry_run(self.user, start_time, end_time)

        self.assertEqual(results["user"], self.user.username)
        # 2 creations, 1 update
        self.assertEqual(results["events_found_n"], 3)
        self.assertEqual(results["start_time"], start_time)
        self.assertEqual(results["end_time"], end_time)
        self.assertEqual(results["events_revertable_n"], 2)
        self.assertEqual(results["events_not_revertable_n"], 1)
        # those events are revertable because they have been made by the same user
        # and are both in the rollback time range.
        self.assertEqual(
            set(results["events_revertable"]),
            set({building_1_creation_event_id, building_1_update_event_id}),
        )
        # not revertable because other_user has updated the building since.
        self.assertEqual(
            results["events_not_revertable"],
            [building_2_creation_event_id],
        )

        results = rollback(self.user, start_time, end_time)

        self.assertEqual(results["user"], self.user.username)
        # 2 creations, 1 update
        self.assertEqual(results["events_found_n"], 3)
        self.assertEqual(results["start_time"], start_time)
        self.assertEqual(results["end_time"], end_time)
        self.assertEqual(results["events_reverted_n"], 2)
        self.assertEqual(results["events_not_revertable_n"], 1)
        # those events are revertable because they have been made by the same user
        # and are both in the rollback time range.
        self.assertEqual(
            set(results["events_reverted"]),
            set({building_1_creation_event_id, building_1_update_event_id}),
        )
        # not revertable because other_user has updated the building since.
        self.assertEqual(
            results["events_not_revertable"],
            [building_2_creation_event_id],
        )

        # check the final state
        self.building_1.refresh_from_db()
        self.assertFalse(self.building_1.is_active)
        self.assertEqual(self.building_1.event_type, EventType.REVERT_CREATION.value)
        self.assertEqual(self.building_1.revert_event_id, building_1_creation_event_id)

        [update_revert] = BuildingWithHistory.objects.filter(
            revert_event_id=building_1_update_event_id
        )
        self.assertEqual(update_revert.event_type, EventType.REVERT_UPDATE.value)

        self.building_2.refresh_from_db()
        self.assertTrue(self.building_2.is_active)
        self.assertEqual(self.building_2.event_type, EventType.UPDATE.value)
        self.assertEqual(self.building_2.revert_event_id, None)

    @override_settings(MAX_BUILDING_AREA=float("inf"))
    def test_dry_rollback_3(self):
        """The same user does multiple editions on the same building. All those updates should be revertable."""
        self.building_2.refresh_from_db()
        start_time = self.building_2.sys_period.lower
        end_time = None
        building_2_creation_event_id = self.building_2.event_id

        # edition 1
        self.building_2.update(
            self.user,
            {"source": "contribution"},
            status="demolished",
            addresses_id=None,
        )
        self.building_2.refresh_from_db()
        building_2_edition_1_event_id = self.building_2.event_id

        # edition 2
        self.building_2.update(
            self.user,
            {"source": "contribution"},
            status="notUsable",
            addresses_id=None,
        )
        self.building_2.refresh_from_db()
        building_2_edition_2_event_id = self.building_2.event_id

        # edition 3
        self.building_2.deactivate(self.user, {"source": "contribution"})
        self.building_2.refresh_from_db()
        building_2_edition_3_event_id = self.building_2.event_id

        # edition 4
        self.building_2.reactivate(self.user, {"source": "contribution"})
        self.building_2.refresh_from_db()
        building_2_edition_4_event_id = self.building_2.event_id

        # edition 5
        child = {
            "status": "constructed",
            "shape": self.shape_1,
            "addresses_cle_interop": [],
        }
        split_childs = self.building_2.split(
            [child, child], self.user, {"source": "contribution"}
        )
        self.building_2.refresh_from_db()
        building_2_edition_5_event_id = self.building_2.event_id

        results = rollback_dry_run(self.user, start_time, end_time)

        self.assertEqual(results["user"], self.user.username)
        # 1 creation, 5 editions (update, update, deactivation, reactivation, split)
        self.assertEqual(results["events_found_n"], 6)
        self.assertEqual(results["start_time"], start_time)
        self.assertEqual(results["end_time"], end_time)
        self.assertEqual(results["events_revertable_n"], 6)
        self.assertEqual(results["events_not_revertable_n"], 0)
        # those events are revertable because they have been made by the same user
        # and are both in the rollback time range.
        self.assertEqual(
            set(results["events_revertable"]),
            set(
                {
                    building_2_creation_event_id,
                    building_2_edition_1_event_id,
                    building_2_edition_2_event_id,
                    building_2_edition_3_event_id,
                    building_2_edition_4_event_id,
                    building_2_edition_5_event_id,
                }
            ),
        )
        # not revertable because other_user has updated the building since.
        self.assertEqual(
            results["events_not_revertable"],
            [],
        )

        # And then other_user updates one child of the final split
        # All events become impossible to revert.
        split_child = split_childs[0]
        split_child.update(
            self.other_user,
            {"source": "contribution"},
            status="demolished",
            addresses_id=None,
        )

        results = rollback_dry_run(self.user, start_time, end_time)
        self.assertEqual(results["events_revertable_n"], 0)
        self.assertEqual(results["events_not_revertable_n"], 6)

        results = rollback(self.user, start_time, end_time)
        self.assertEqual(results["events_reverted_n"], 0)
        self.assertEqual(results["events_not_revertable_n"], 6)

    @override_settings(MAX_BUILDING_AREA=float("inf"))
    def test_global_rollback_3(self):
        """The same user does multiple editions on the same building. All those updates should be revertable."""
        self.building_2.refresh_from_db()
        start_time = self.building_2.sys_period.lower
        end_time = None
        building_2_creation_event_id = self.building_2.event_id

        # edition 1
        self.building_2.update(
            self.user,
            {"source": "contribution"},
            status="demolished",
            addresses_id=None,
        )
        self.building_2.refresh_from_db()
        building_2_edition_1_event_id = self.building_2.event_id

        # edition 2
        self.building_2.update(
            self.user,
            {"source": "contribution"},
            status="notUsable",
            addresses_id=None,
        )
        self.building_2.refresh_from_db()
        building_2_edition_2_event_id = self.building_2.event_id

        # edition 3
        self.building_2.deactivate(self.user, {"source": "contribution"})
        self.building_2.refresh_from_db()
        building_2_edition_3_event_id = self.building_2.event_id

        # edition 4
        self.building_2.reactivate(self.user, {"source": "contribution"})
        self.building_2.refresh_from_db()
        building_2_edition_4_event_id = self.building_2.event_id

        # edition 5
        child = {
            "status": "constructed",
            "shape": self.shape_1,
            "addresses_cle_interop": [],
        }
        split_childs = self.building_2.split(
            [child, child], self.user, {"source": "contribution"}
        )
        self.building_2.refresh_from_db()
        building_2_edition_5_event_id = self.building_2.event_id

        results = rollback(self.user, start_time, end_time)

        self.assertEqual(results["user"], self.user.username)
        # 1 creation, 5 editions (update, update, deactivation, reactivation, split)
        self.assertEqual(results["events_found_n"], 6)
        self.assertEqual(results["start_time"], start_time)
        self.assertEqual(results["end_time"], end_time)
        self.assertEqual(results["events_reverted_n"], 6)
        self.assertEqual(results["events_not_revertable_n"], 0)
        # those events are revertable because they have been made by the same user
        # and are both in the rollback time range.
        self.assertEqual(
            set(results["events_reverted"]),
            set(
                {
                    building_2_creation_event_id,
                    building_2_edition_1_event_id,
                    building_2_edition_2_event_id,
                    building_2_edition_3_event_id,
                    building_2_edition_4_event_id,
                    building_2_edition_5_event_id,
                }
            ),
        )
        # not revertable because other_user has updated the building since.
        self.assertEqual(
            results["events_not_revertable"],
            [],
        )

        child_events = Building.child_events_from_event_id(
            building_2_edition_5_event_id
        )
        # 6 events to revert, 6 new events expected
        self.assertEqual(len(child_events), 6)

        self.building_2.refresh_from_db()
        # final state expected
        self.assertEqual(self.building_2.event_type, EventType.REVERT_CREATION.value)
        self.assertEqual(self.building_2.status, "constructed")
        self.assertFalse(self.building_2.is_active)

    def test_global_rollback_4(self):
        """Here a user creates 2 buildings and then update one of the created building.
        We ask for a rollback that excludes the update (via the end_time).
        Expected : only one creation can be rolled back.
        """
        self.building_1.refresh_from_db()
        self.building_2.refresh_from_db()
        start_time = self.building_1.sys_period.lower
        end_time = self.building_2.sys_period.lower

        building_1_creation_event_id = self.building_1.event_id
        building_2_creation_event_id = self.building_2.event_id

        # the building is updated by the same user
        self.building_1.update(
            self.user,
            {"source": "contribution"},
            status="demolished",
            addresses_id=None,
        )
        self.building_1.refresh_from_db()

        results = rollback_dry_run(self.user, start_time, end_time)

        self.assertEqual(results["user"], self.user.username)
        # 2 creations (the update is outside the range)
        self.assertEqual(results["events_found_n"], 2)
        self.assertEqual(results["start_time"], start_time)
        self.assertEqual(results["end_time"], end_time)
        # building_2 creation
        self.assertEqual(results["events_revertable_n"], 1)
        # building_1 creation and update because the update is outside the time range
        self.assertEqual(results["events_not_revertable_n"], 1)
        self.assertEqual(
            set(results["events_revertable"]),
            set({building_2_creation_event_id}),
        )
        # not revertable because the building has been updated after the rollback range.
        self.assertEqual(
            results["events_not_revertable"],
            [building_1_creation_event_id],
        )

        results = rollback(self.user, start_time, end_time)

        self.assertEqual(results["user"], self.user.username)
        self.assertEqual(results["events_found_n"], 2)
        self.assertEqual(results["start_time"], start_time)
        self.assertEqual(results["end_time"], end_time)
        self.assertEqual(results["events_reverted_n"], 1)
        self.assertEqual(results["events_not_revertable_n"], 1)
        self.assertEqual(results["events_reverted"], [building_2_creation_event_id])
        self.assertEqual(
            results["events_not_revertable"],
            [building_1_creation_event_id],
        )

        # check the final state
        self.building_1.refresh_from_db()
        self.assertTrue(self.building_1.is_active)
        self.assertEqual(self.building_1.event_type, EventType.UPDATE.value)

        self.building_2.refresh_from_db()
        self.assertFalse(self.building_2.is_active)
        self.assertEqual(self.building_2.event_type, EventType.REVERT_CREATION.value)
        self.assertEqual(self.building_2.revert_event_id, building_2_creation_event_id)
