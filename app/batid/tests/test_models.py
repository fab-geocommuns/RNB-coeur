import datetime
import json

from django.contrib.gis.geos import GEOSGeometry
from django.db.utils import IntegrityError
from django.test import override_settings
from django.test import TestCase

from batid.exceptions import OperationOnInactiveBuilding
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
        Simplest test of deactivation.
        """
        bdg = Building.objects.create(rnb_id="AAA", shape="POINT(0 0)")

        user = User.objects.create_user(username="dummy")

        bdg.deactivate(user, {"k": "v"})
        bdg.refresh_from_db()

        self.assertFalse(bdg.is_active)
        self.assertEqual(bdg.event_user, user)
        self.assertEqual(bdg.event_type, "deactivation")
        self.assertEqual(bdg.event_origin, {"k": "v"})
        self.assertIsNotNone(bdg.event_id)

    def test_no_deactivate_inactive_buildings(self):
        """
        An inactive building deactivation is ignored.
        """
        bdg = Building.objects.create(rnb_id="AAA", shape="POINT(0 0)", is_active=False)
        user = User.objects.create_user(username="dummy")
        with self.assertRaises(OperationOnInactiveBuilding):
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
        Test some scenario with contributions linked (or not) to deactivated building.
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

    def test_building_event_types(self):
        # you can't save whatever imaginary event type in the DB
        with self.assertRaises(IntegrityError):
            Building.objects.create(rnb_id="XYZ", event_type="new!")

    def test_update_building_event_types(self):
        b = Building.objects.create(rnb_id="XYZ", event_type="creation")

        with self.assertRaises(IntegrityError):
            # that type does not exist
            b.event_type = "spawn"
            b.save()


class TestSplitBuilding(TestCase):
    def setUp(self):
        self.user = User()
        self.user.save()
        self.adr1 = Address.objects.create(id="cle_interop_1")
        self.adr2 = Address.objects.create(id="cle_interop_2")

    @override_settings(MAX_BUILDING_AREA=float("inf"))
    def test_split_a_building(self):
        # create a building
        b1 = Building.objects.create(rnb_id="1", status="constructed")
        event_origin = {"source": "xxx"}
        # split it in 3
        created_buildings = b1.split(
            [
                {
                    "status": "constructed",
                    "addresses_cle_interop": [],
                    "shape": "POLYGON((0 0, 0 2, 2 2, 2 0, 0 0))",
                },
                {
                    "status": "demolished",
                    # duplicate on purpose
                    "addresses_cle_interop": [self.adr1.id, self.adr1.id],
                    "shape": "POINT(0 1)",
                },
                {
                    "status": "constructionProject",
                    "addresses_cle_interop": [self.adr1.id, self.adr2.id],
                    "shape": "POLYGON((0 0, 0 1, 1 1, 1 0, 0 0))",
                },
            ],
            self.user,
            event_origin,
        )

        b1.refresh_from_db()
        event_id = b1.event_id

        self.assertEqual(len(created_buildings), 3)

        b2 = created_buildings[0]
        b3 = created_buildings[1]
        b4 = created_buildings[2]

        self.assertEqual(b1.event_origin, event_origin)
        self.assertEqual(b1.parent_buildings, None)
        self.assertEqual(b1.status, "constructed")
        self.assertEqual(b1.event_id, event_id)
        self.assertEqual(b1.event_origin, event_origin)
        self.assertEqual(b1.event_type, "split")
        self.assertEqual(b1.event_user, self.user)
        self.assertFalse(b1.is_active)
        self.assertEqual(b1.addresses_id, None)

        self.assertEqual(b2.point.wkt, "POINT (1 1)")
        self.assertEqual(b2.shape.wkt, "POLYGON ((0 0, 0 2, 2 2, 2 0, 0 0))")
        self.assertEqual(b2.event_origin, event_origin)
        self.assertEqual(b2.parent_buildings, [b1.rnb_id])
        self.assertEqual(b2.status, "constructed")
        self.assertEqual(b2.event_id, event_id)
        self.assertEqual(b2.event_origin, event_origin)
        self.assertEqual(b2.event_type, "split")
        self.assertEqual(b2.event_user, self.user)
        self.assertTrue(b2.is_active)
        self.assertEqual(b2.addresses_id, [])

        self.assertEqual(b3.point.wkt, "POINT (0 1)")
        self.assertEqual(b3.shape.wkt, "POINT (0 1)")
        self.assertEqual(b3.event_origin, event_origin)
        self.assertEqual(b3.parent_buildings, [b1.rnb_id])
        self.assertEqual(b3.status, "demolished")
        self.assertEqual(b3.event_id, event_id)
        self.assertEqual(b3.event_origin, event_origin)
        self.assertEqual(b3.event_type, "split")
        self.assertEqual(b3.event_user, self.user)
        self.assertTrue(b3.is_active)
        self.assertEqual(b3.addresses_id, [self.adr1.id])

        self.assertEqual(b4.point.wkt, "POINT (0.5 0.5)")
        self.assertEqual(b4.shape.wkt, "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))")
        self.assertEqual(b4.event_origin, event_origin)
        self.assertEqual(b4.parent_buildings, [b1.rnb_id])
        self.assertEqual(b4.status, "constructionProject")
        self.assertEqual(b4.event_id, event_id)
        self.assertEqual(b4.event_origin, event_origin)
        self.assertEqual(b4.event_type, "split")
        self.assertEqual(b4.event_user, self.user)
        self.assertTrue(b4.is_active)
        self.assertEqual(b4.addresses_id.sort(), [self.adr1.id, self.adr2.id].sort())

    def test_split_a_building_raise(self):
        # create building
        b1 = Building.objects.create(rnb_id="1", status="constructed")
        event_origin = {"source": "xxx"}

        with self.assertRaisesRegex(
            Exception, "A building must be split at least in two"
        ):
            # cannot split in 1
            b1.split(
                [
                    {
                        "status": "constructed",
                        "addresses_cle_interop": [],
                        "shape": "POLYGON((0 0, 0 2, 2 2, 2 0, 0 0))",
                    }
                ],
                self.user,
                event_origin,
            )

    def test_split_a_building_inactive(self):
        # create building
        b1 = Building.objects.create(rnb_id="1", status="constructed", is_active=False)
        event_origin = {"source": "xxx"}

        with self.assertRaisesRegex(Exception, "Cannot split inactive building 1"):
            b1.split(
                [
                    {
                        "status": "constructed",
                        "addresses_cle_interop": [],
                        "shape": "POLYGON((0 0, 0 2, 2 2, 2 0, 0 0))",
                    },
                    {
                        "status": "constructed",
                        "addresses_cle_interop": [],
                        "shape": "POLYGON((0 0, 0 2, 2 2, 2 0, 0 0))",
                    },
                ],
                self.user,
                event_origin,
            )


class TestUpdateBuilding(TestCase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.rnb_id = None
        self.user = None

    def setUp(self):

        Address.objects.create(id="addr1")
        Address.objects.create(id="addr2")
        Address.objects.create(id="addr3")

        self.user = User.objects.create_user(username="solo_user")

        b = Building.create_new(
            user=self.user,
            event_origin={"source": "dummy_creation"},
            status="constructed",
            addresses_id=["addr1", "addr2"],
            shape=GEOSGeometry(
                json.dumps(
                    {
                        "coordinates": [
                            [
                                [-0.5629838649124963, 44.89830737784746],
                                [-0.5627894800164768, 44.89622105788288],
                                [-0.5603213808721534, 44.89635458462783],
                                [-0.5605098753173934, 44.89844507230214],
                                [-0.5629838649124963, 44.89830737784746],
                            ]
                        ],
                        "type": "Polygon",
                    }
                )
            ),
            ext_ids=[],
        )

        self.rnb_id = b.rnb_id

    def test_updated_at(self):
        """
        Test that the updated_at field is set when updating a building.
        """
        b = Building.objects.get(rnb_id=self.rnb_id)
        old_updated_at = b.updated_at

        print(f"Old updated_at: {old_updated_at}")

        # Update the building

        b.update(
            user=self.user,
            status="demolished",
            event_origin={"source": "dummy_update"},
            addresses_id=None,
        )

        b.refresh_from_db()

        print(f"New updated_at: {b.updated_at}")
        self.assertNotEqual(b.updated_at, old_updated_at)
