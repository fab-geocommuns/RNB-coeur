from django.test import TestCase

from batid.models import Address
from batid.models import Building
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
            ext_ids=[{"source": "bdtopo", "id": "2"}],
        )

        address = Address.objects.create()

        # merge the two buildings
        merged_building = Building.merge(
            [building_1, building_2],
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
            merged_building.parent_buildings, [building_1.rnb_id, building_2.rnb_id]
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
