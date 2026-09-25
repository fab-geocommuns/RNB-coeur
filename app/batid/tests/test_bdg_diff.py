from batid.models import Building
from batid.services.bdg_diff import building_identicals, buildings_diff_fields
from django.contrib.gis.geos import GEOSGeometry
from django.test import TestCase

SHAPE_WKT = "3.702622150150296 49.304784015647726, 3.702693383202145 49.3048663059031, 3.702798693694756 49.30482613857543, 3.702734346050333 49.30474470727255, 3.702622150150296 49.304784015647726"


class IdenticalBdgVersionsDetection(TestCase):
    def test_rnb_id_not_identical(self):
        """
        Input: two buildings with different rnb_id.
        Expected: diff is {"rnb_id"}, buildings are not identical.
        """
        b1 = Building(rnb_id="rnb_id_1")
        b2 = Building(rnb_id="rnb_id_2")
        self.assertEqual(buildings_diff_fields(b1, b2), set(["rnb_id"]))
        self.assertFalse(building_identicals(b1, b2))

    def test_rnb_id_identical(self):
        """
        Input: two buildings with the same rnb_id.
        Expected: empty diff, buildings are identical.
        """
        b1 = Building(rnb_id="rnb_id")
        b2 = Building(rnb_id="rnb_id")
        self.assertEqual(buildings_diff_fields(b1, b2), set([]))
        self.assertTrue(building_identicals(b1, b2))

    def test_point_not_identical(self):
        """
        Input: two buildings whose points differ on the last decimal.
        Expected: diff is {"point"}, buildings are not identical.
        """
        p1 = GEOSGeometry("POINT (3.702711216191982 49.30480507711158)")
        p2 = GEOSGeometry("POINT (3.702711216191982 49.30480507711157)")
        b1 = Building(point=p1)
        b2 = Building(point=p2)
        self.assertEqual(buildings_diff_fields(b1, b2), set(["point"]))
        self.assertFalse(building_identicals(b1, b2))

    def test_point_identical(self):
        """
        Input: two buildings with the same point.
        Expected: empty diff, buildings are identical.
        """
        p1 = GEOSGeometry("POINT (3.702711216191982 49.30480507711158)")
        p2 = GEOSGeometry("POINT (3.702711216191982 49.30480507711158)")
        b1 = Building(point=p1)
        b2 = Building(point=p2)
        self.assertEqual(buildings_diff_fields(b1, b2), set([]))
        self.assertTrue(building_identicals(b1, b2))

    def test_shape_not_identical(self):
        """
        Input: same coordinates, one shape as a MULTIPOLYGON, the other as a POLYGON.
        Expected: diff is {"shape"}, buildings are not identical.
        """
        s1 = GEOSGeometry(f"MULTIPOLYGON ((({SHAPE_WKT})))")
        s2 = GEOSGeometry(f"POLYGON (({SHAPE_WKT}))")
        b1 = Building(shape=s1)
        b2 = Building(shape=s2)
        self.assertEqual(buildings_diff_fields(b1, b2), set(["shape"]))
        self.assertFalse(building_identicals(b1, b2))

    def test_shape_identical(self):
        """
        Input: two buildings with the same MULTIPOLYGON shape.
        Expected: empty diff, buildings are identical.
        """
        s1 = GEOSGeometry(f"MULTIPOLYGON ((({SHAPE_WKT})))")
        s2 = GEOSGeometry(f"MULTIPOLYGON ((({SHAPE_WKT})))")
        b1 = Building(shape=s1)
        b2 = Building(shape=s2)
        self.assertEqual(buildings_diff_fields(b1, b2), set([]))
        self.assertTrue(building_identicals(b1, b2))

    def test_parents_not_identical(self):
        """
        Input: parent_buildings lists with a different element, or one list empty
        (compared in both directions).
        Expected: diff is {"parent_buildings"}, buildings are not identical.
        """
        b1 = Building(parent_buildings=["parent1", "parent2"])
        b2 = Building(parent_buildings=["parent1", "parent3"])
        self.assertEqual(buildings_diff_fields(b1, b2), set(["parent_buildings"]))
        self.assertFalse(building_identicals(b1, b2))

        # One is empty (we test that the order is not important)
        b3 = Building(parent_buildings=[])
        self.assertEqual(buildings_diff_fields(b1, b3), set(["parent_buildings"]))
        self.assertFalse(building_identicals(b1, b3))
        self.assertEqual(buildings_diff_fields(b3, b1), set(["parent_buildings"]))
        self.assertFalse(building_identicals(b3, b1))

    def test_parents_identical(self):
        """
        Input: same parent_buildings in the same order, in a different order,
        and both null.
        Expected: empty diff, buildings are identical in each case.
        """
        # Same order
        b1 = Building(parent_buildings=["parent1", "parent2"])
        b2 = Building(parent_buildings=["parent1", "parent2"])
        self.assertEqual(buildings_diff_fields(b1, b2), set([]))
        self.assertTrue(building_identicals(b1, b2))

        # Different order
        b3 = Building(parent_buildings=["parent2", "parent1"])
        self.assertEqual(buildings_diff_fields(b1, b3), set([]))
        self.assertTrue(building_identicals(b1, b3))

        # Both null
        b4 = Building(parent_buildings=None)
        b5 = Building()
        self.assertEqual(buildings_diff_fields(b4, b5), set([]))
        self.assertTrue(building_identicals(b4, b5))

    def test_ext_id_not_identical(self):
        """
        Input: ext_ids with a different id, empty, null, or with an extra element.
        Expected: diff is {"ext_ids"}, buildings are not identical in each case.
        """
        b1 = Building(ext_ids=[{"id": "id1", "source": "source1"}])
        b2 = Building(ext_ids=[{"id": "id2", "source": "source1"}])
        self.assertEqual(buildings_diff_fields(b1, b2), set(["ext_ids"]))
        self.assertFalse(building_identicals(b1, b2))

        # One is empty
        b3 = Building(ext_ids=[])
        self.assertEqual(buildings_diff_fields(b1, b3), set(["ext_ids"]))
        self.assertFalse(building_identicals(b1, b3))

        # One is null
        b4 = Building(ext_ids=None)
        self.assertEqual(buildings_diff_fields(b1, b4), set(["ext_ids"]))
        self.assertFalse(building_identicals(b1, b4))

        # One has an extra ext_id
        b5 = Building(
            ext_ids=[
                {"id": "id1", "source": "source1"},
                {"id": "id1", "source": "source2"},
            ]
        )
        self.assertEqual(buildings_diff_fields(b1, b5), set(["ext_ids"]))
        self.assertFalse(building_identicals(b1, b5))

    def test_ext_id_identical(self):
        """
        Input: same ext_ids in the same order, then in a different order.
        Expected: empty diff, buildings are identical in both cases.
        """
        # Same order
        b1 = Building(
            ext_ids=[
                {"id": "id1", "source": "source1"},
                {"id": "id2", "source": "source1"},
            ]
        )
        b2 = Building(
            ext_ids=[
                {"id": "id1", "source": "source1"},
                {"id": "id2", "source": "source1"},
            ]
        )
        self.assertEqual(buildings_diff_fields(b1, b2), set([]))
        self.assertTrue(building_identicals(b1, b2))

        # Different order
        b3 = Building(
            ext_ids=[
                {"id": "id2", "source": "source1"},
                {"id": "id1", "source": "source1"},
            ]
        )
        self.assertEqual(buildings_diff_fields(b1, b3), set([]))
        self.assertTrue(building_identicals(b1, b3))

    def test_is_active_not_identical(self):
        """
        Input: one active building, one inactive.
        Expected: diff is {"is_active"}, buildings are not identical.
        """
        b1 = Building(is_active=True)
        b2 = Building(is_active=False)
        self.assertEqual(buildings_diff_fields(b1, b2), set(["is_active"]))
        self.assertFalse(building_identicals(b1, b2))

    def test_is_active_identical(self):
        """
        Input: both buildings active, then both inactive.
        Expected: empty diff, buildings are identical in both cases.
        """
        # Both True
        b1 = Building(is_active=True)
        b2 = Building(is_active=True)
        self.assertEqual(buildings_diff_fields(b1, b2), set([]))
        self.assertTrue(building_identicals(b1, b2))

        # Both False
        b3 = Building(is_active=False)
        b4 = Building(is_active=False)
        self.assertEqual(buildings_diff_fields(b3, b4), set([]))
        self.assertTrue(building_identicals(b3, b4))

    def test_addresses_internal_id_identical(self):
        """
        Input: same addresses_internal_id in the same order, in a different order,
        and both null.
        Expected: empty diff, buildings are identical in each case.
        """
        # Same order
        b1 = Building(addresses_internal_id=[1, 2])
        b2 = Building(addresses_internal_id=[1, 2])
        self.assertEqual(buildings_diff_fields(b1, b2), set([]))
        self.assertTrue(building_identicals(b1, b2))

        # Different order
        b3 = Building(addresses_internal_id=[2, 1])
        self.assertEqual(buildings_diff_fields(b1, b3), set([]))
        self.assertTrue(building_identicals(b1, b3))

        # Both null
        b4 = Building(addresses_internal_id=None)
        b5 = Building()
        self.assertEqual(buildings_diff_fields(b4, b5), set([]))
        self.assertTrue(building_identicals(b4, b5))

    def test_addresses_internal_id_not_identical(self):
        """
        Input: addresses_internal_id with a different element, empty, null,
        or with an extra element.
        Expected: diff is {"addresses_internal_id"}, buildings are not identical
        in each case.
        """
        b1 = Building(addresses_internal_id=[1, 2])
        b2 = Building(addresses_internal_id=[1, 3])
        self.assertEqual(buildings_diff_fields(b1, b2), set(["addresses_internal_id"]))
        self.assertFalse(building_identicals(b1, b2))

        # One is empty
        b3 = Building(addresses_internal_id=[])
        self.assertEqual(buildings_diff_fields(b1, b3), set(["addresses_internal_id"]))
        self.assertFalse(building_identicals(b1, b3))

        # One is null
        b4 = Building(addresses_internal_id=None)
        self.assertEqual(buildings_diff_fields(b1, b4), set(["addresses_internal_id"]))
        self.assertFalse(building_identicals(b1, b4))

        # One has an extra address
        b5 = Building(addresses_internal_id=[1, 2, 3])
        self.assertEqual(buildings_diff_fields(b1, b5), set(["addresses_internal_id"]))
        self.assertFalse(building_identicals(b1, b5))

    def test_event_id_not_identical(self):
        """
        Input: two buildings with different event_id.
        Expected: diff is {"event_id"}, buildings are not identical.
        """
        b1 = Building(event_id="id1")
        b2 = Building(event_id="id2")
        self.assertEqual(buildings_diff_fields(b1, b2), set(["event_id"]))
        self.assertFalse(building_identicals(b1, b2))

    def test_event_id_identical(self):
        """
        Input: two buildings with the same event_id.
        Expected: empty diff, buildings are identical.
        """
        b1 = Building(event_id="id1")
        b2 = Building(event_id="id1")
        self.assertEqual(buildings_diff_fields(b1, b2), set([]))
        self.assertTrue(building_identicals(b1, b2))

    def test_event_type_not_identical(self):
        """
        Input: two buildings with different event_type, then one with a null event_type.
        Expected: diff is {"event_type"}, buildings are not identical in both cases.
        """
        b1 = Building(event_type="type1")
        b2 = Building(event_type="type2")
        self.assertEqual(buildings_diff_fields(b1, b2), set(["event_type"]))
        self.assertFalse(building_identicals(b1, b2))

        # One is null
        b3 = Building(event_type=None)
        self.assertEqual(buildings_diff_fields(b1, b3), set(["event_type"]))
        self.assertFalse(building_identicals(b1, b3))
