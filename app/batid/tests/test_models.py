import datetime

from django.test import TestCase

from batid.models import Address
from batid.models import Building
from batid.models import Contribution
from batid.models import User


class TestBuilding(TestCase):
    def test_merge_buildings(self):
        user = User.objects.create_user(username="Léon Marchand")

        # create two contiguous buildings
        building_1 = Building.objects.create(
            rnb_id="AAA",
            shape="POLYGON((0 0, 0 1, 1 1, 1 0, 0 0))",
            ext_ids=[{"source": "bdtopo", "id": "1"}],
        )
        building_2 = Building.objects.create(
            rnb_id="BBB",
            shape="POLYGON((1 0, 1 1, 2 1, 2 0, 1 0))",
            ext_ids=[{"source": "bdtopo", "id": "1"}, {"source": "bdtopo", "id": "2"}],
        )
        building_3 = Building.objects.create(
            rnb_id="CCC"
            # no shape, to check the function does not crash in that case
            # even that case is unexpected
        )

        address = Address.objects.create()

        # merge the two buildings
        merged_building = Building.merge(
            [building_1, building_2, building_3],
            user,
            {"source": "contribution", "contribution_id": 1},
            "constructed",
            [address.id],
        )

        building_1.refresh_from_db()
        building_2.refresh_from_db()

        event_id = merged_building.event_id

        # assert building_1 properties
        self.assertEqual(building_1.event_id, event_id)
        self.assertEqual(building_1.event_type, "merge")
        self.assertEqual(
            building_1.event_origin, {"source": "contribution", "contribution_id": 1}
        )
        self.assertEqual(building_1.event_user, user)
        self.assertEqual(building_1.is_active, False)

        # assert building_2 properties
        self.assertEqual(building_2.event_id, event_id)
        self.assertEqual(building_2.event_type, "merge")
        self.assertEqual(
            building_2.event_origin, {"source": "contribution", "contribution_id": 1}
        )
        self.assertEqual(building_2.event_user, user)
        self.assertEqual(building_2.is_active, False)

        # assert created building properties
        self.assertTrue(merged_building.point)
        self.assertTrue(merged_building.shape)
        self.assertTrue(merged_building.shape)
        self.assertEqual(
            merged_building.ext_ids,
            [{"source": "bdtopo", "id": "1"}, {"source": "bdtopo", "id": "2"}],
        )
        self.assertEqual(
            merged_building.event_origin,
            {"source": "contribution", "contribution_id": 1},
        )
        self.assertEqual(
            merged_building.parent_buildings,
            [building_1.rnb_id, building_2.rnb_id, building_3.rnb_id],
        )
        self.assertEqual(merged_building.status, "constructed")
        self.assertEqual(merged_building.event_type, "merge")
        self.assertEqual(merged_building.event_user, user)
        self.assertEqual(merged_building.is_active, True)

    def test_merge_buildings_not_enough_buildings(self):
        building = Building.objects.create(
            rnb_id="AAA",
            shape="POLYGON((0 0, 0 1, 1 1, 1 0, 0 0))",
            ext_ids=[{"source": "bdtopo", "id": "1"}],
        )

        with self.assertRaises(Exception):
            Building.merge([building], None, {}, "constructed", [])

    def test_merge_buildings_inactive_buildings(self):
        building = Building.objects.create(
            rnb_id="AAA",
            is_active=False,
            shape="POLYGON((0 0, 0 1, 1 1, 1 0, 0 0))",
        )

        with self.assertRaises(Exception) as e:
            Building.merge([building], None, {}, "constructed", [])
            self.assertEqual(
                str(e),
                f"Cannot merge inactive buildings.",
            )

    def test_deactivate(self):
        """
        Simplest test of the soft delete.
        """
        bdg = Building.objects.create(rnb_id="AAA", shape="POINT(0 0)")

        user = User.objects.create_user(username="dummy")

        bdg.deactivate(user, {"k": "v"})
        bdg.refresh_from_db()

        self.assertFalse(bdg.is_active)
        self.assertEqual(bdg.event_user, user)
        self.assertEqual(bdg.event_type, "delete")
        self.assertEqual(bdg.event_origin, {"k": "v"})
        self.assertIsNotNone(bdg.event_id)

    def test_no_deactivate_inactive_buildings(self):
        """
        An inactive building soft-delete is ignored.
        """
        bdg = Building.objects.create(rnb_id="AAA", shape="POINT(0 0)", is_active=False)
        user = User.objects.create_user(username="dummy")
        bdg.deactivate(user, {"k": "v"})
        bdg.refresh_from_db()

        # nothing has changed
        self.assertFalse(bdg.is_active)
        self.assertIsNone(bdg.event_user)
        self.assertIsNone(bdg.event_type)
        self.assertIsNone(bdg.event_origin)
        self.assertIsNone(bdg.event_id)

    def test_deactivate_with_contributions(self):
        """
        Test some scenario with contributions linked (or not) to soft deleted building.
        """
        bdg = Building.objects.create(rnb_id="AAA", shape="POINT(0 0)")

        user = User.objects.create_user(username="dummy")

        # This is pending, it must be refused after deactivation
        contrib_pending = Contribution.objects.create(
            rnb_id="AAA", status="pending", text="dummy"
        )

        # This is already fixed. It must keep its status
        contrib_fixed = Contribution.objects.create(
            rnb_id="AAA", status="fixed", text="fixed dummy"
        )

        # This is pending but on another building. It must keep its status
        contrib_other_bdg = Contribution.objects.create(
            rnb_id="BBB", status="pending", text="dummy"
        )

        bdg.deactivate(user, {"k": "v"})

        # Check the first contrib has changed after the deactivation
        contrib_pending.refresh_from_db()
        self.assertEqual(contrib_pending.status, "refused")
        self.assertEqual(contrib_pending.review_user, user)
        self.assertEqual(
            contrib_pending.review_comment,
            "Ce signalement a été refusé suite à la désactivation du bâtiment AAA.",
        )
        self.assertIsInstance(contrib_pending.status_changed_at, datetime.datetime)

        # Check the fixed contributions is still fixed
        contrib_fixed.refresh_from_db()
        self.assertEqual(contrib_fixed.status, "fixed")

        # Check the other building contribution is still pending
        contrib_other_bdg.refresh_from_db()
        self.assertEqual(contrib_other_bdg.status, "pending")
