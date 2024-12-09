from django.contrib.auth.models import User
from django.contrib.gis.geos import GEOSGeometry
from django.test import TestCase
from django.test import TransactionTestCase

from batid.models import Address
from batid.models import Building
from batid.models import BuildingWithHistory
from batid.services.data_fix.fill_empty_event_origin import building_identicals
from batid.services.data_fix.fill_empty_event_origin import buildings_diff_fields
from batid.services.data_fix.fill_empty_event_origin import fix


class FixMissingEventOriginTest(TransactionTestCase):
    def test_fill_empty_event_origin(self):

        rnb_id_1 = insert_building_history_1()
        rnb_id_2 = insert_building_history_2()
        rnb_id_3 = insert_building_history_3()
        rnb_id_4 = insert_building_history_4()
        rnb_id_5 = insert_building_history_5()

        initial_buildings_1 = list(
            BuildingWithHistory.objects.all()
            .filter(rnb_id=rnb_id_1)
            .order_by("sys_period")
        )
        initial_buildings_2 = list(
            BuildingWithHistory.objects.all()
            .filter(rnb_id=rnb_id_2)
            .order_by("sys_period")
        )
        initial_buildings_3 = list(
            BuildingWithHistory.objects.all()
            .filter(rnb_id=rnb_id_3)
            .order_by("sys_period")
        )
        initial_buildings_4 = list(
            BuildingWithHistory.objects.all()
            .filter(rnb_id=rnb_id_4)
            .order_by("sys_period")
        )

        # we set a small batch size, to check the loop is working properly
        fix(batch_size=1)

        # three versions have been squashed together
        fixed_buildings_1 = (
            BuildingWithHistory.objects.all()
            .filter(rnb_id=rnb_id_1)
            .order_by("sys_period")
        )
        fixed_buildings_2 = (
            BuildingWithHistory.objects.all()
            .filter(rnb_id=rnb_id_2)
            .order_by("sys_period")
        )
        fixed_buildings_3 = (
            BuildingWithHistory.objects.all()
            .filter(rnb_id=rnb_id_3)
            .order_by("sys_period")
        )
        fixed_buildings_4 = (
            BuildingWithHistory.objects.all()
            .filter(rnb_id=rnb_id_4)
            .order_by("sys_period")
        )

        assertions_for_building_1(self, initial_buildings_1, fixed_buildings_1)
        assertions_for_building_2(self, initial_buildings_2, fixed_buildings_2)
        assertions_for_building_3(self, initial_buildings_3, fixed_buildings_3)
        assertions_for_building_4(self, initial_buildings_4, fixed_buildings_4)
        self.assertions_for_building_5(rnb_id_5)

    def assertions_for_building_5(self, child_rnb_id):
        # The child should be untouched
        child_history = BuildingWithHistory.objects.filter(rnb_id=child_rnb_id)
        self.assertEqual(len(child_history), 1)

        # Assert parent 1
        p1_history = BuildingWithHistory.objects.filter(rnb_id="PARENT_1").order_by(
            "sys_period"
        )
        # We have only 3 versions remaining. Initially we had 5 (4 written in test + merge)
        self.assertEqual(len(p1_history), 3)
        self.assertEqual(p1_history[0].event_type, "creation")
        self.assertEqual(p1_history[1].event_type, "update")
        self.assertEqual(p1_history[2].event_type, "merge")

        # Assert parent 2
        p2_history = BuildingWithHistory.objects.filter(rnb_id="PARENT_2").order_by(
            "sys_period"
        )
        # We have only 2 versions remaining. Initially we had 3 (2 written in test + merge)
        self.assertEqual(len(p2_history), 2)
        self.assertEqual(p2_history[0].event_type, "creation")
        self.assertEqual(p2_history[1].event_type, "merge")


def insert_building_history_1():
    # a case with multiple updates, some squashing needed
    rnb_id = "1C23HEP2JDF2"
    Address.objects.create(id="51250_0027_00007")
    Address.objects.create(id="51250_0027_00008")

    # creation
    b = Building.objects.create(
        rnb_id=rnb_id,
        point="POINT (3.702711216191982 49.30480507711158)",
        created_at="2023-12-11 04:00:35.005 +0100",
        updated_at="2023-12-11 04:00:35.005 +0100",
        shape="MULTIPOLYGON (((3.702622150150296 49.304784015647726, 3.702693383202145 49.3048663059031, 3.702798693694756 49.30482613857543, 3.702734346050333 49.30474470727255, 3.702622150150296 49.304784015647726)))",
        ext_ids='[{"id": "bdnb-bc-SSW2-CGZB-QYUT", "source": "bdnb", "created_at": "2023-12-09T23:01:05.518305+00:00", "source_version": "2023_01"}]',
        event_origin={"id": 151, "source": "import"},
        status="constructed",
        is_active=True,
    )

    # 1st update, we add an ext_id, change the event_origin and fill addresses_id
    b.ext_ids = [
        {
            "id": "bdnb-bc-SSW2-CGZB-QYUT",
            "source": "bdnb",
            "created_at": "2023-12-09T23:01:05.518305+00:00",
            "source_version": "2023_01",
        },
        {
            "id": "BATIMENT0000002291948531",
            "source": "bdtopo",
            "created_at": "2023-12-21T11:39:40.876407+00:00",
            "source_version": "bdtopo_2023_09",
        },
    ]
    b.event_origin = {"id": 248, "source": "import"}
    b.addresses_id = ["51250_0027_00007", "51250_0027_00008"]
    b.save()

    # 2nd update, we add another ext_id, change the event_origin and change the addresses_id order
    b.ext_ids = [
        {
            "id": "bdnb-bc-SSW2-CGZB-QYUT",
            "source": "bdnb",
            "created_at": "2023-12-09T23:01:05.518305+00:00",
            "source_version": "2023_01",
        },
        {
            "id": "BATIMENT0000002291948531",
            "source": "bdtopo",
            "created_at": "2023-12-21T11:39:40.876407+00:00",
            "source_version": "bdtopo_2023_09",
        },
        {
            "id": "BATIMENT0000002340683062",
            "source": "bdtopo",
            "created_at": "2024-06-21T16:44:41.699913+00:00",
            "source_version": "2024-03-15",
        },
    ]
    b.event_origin = {"id": 470, "source": "import"}
    b.addresses_id = ["51250_0027_00008", "51250_0027_00007"]
    b.save()

    # 3rd update, nothing but event_origin
    b.event_origin = {"id": 468, "source": "import"}
    # (order is not imortant)
    b.addresses_id = ["51250_0027_00007", "51250_0027_00008"]

    b.save()

    # 4th update, nothing but event_origin
    b.event_origin = {"id": 523, "source": "import"}
    b.save()

    return rnb_id


def assertions_for_building_1(self, initial_buildings, fixed_buildings):

    # We expect 3 rows to be squashed together, reducing the version count from 5 to 3
    self.assertEqual(len(initial_buildings), 5)
    self.assertEqual(len(fixed_buildings), 3)

    [v0, v1, v2, v3, v4] = initial_buildings
    [f0, f1, f2] = fixed_buildings

    self.assertEqual(f0.event_type, "creation")
    self.assertEqual(buildings_diff_fields(v0, f0), set(["event_type"]))

    self.assertEqual(f1.event_type, "update")
    self.assertEqual(buildings_diff_fields(v1, f1), set(["event_type"]))

    self.assertEqual(f2.event_type, "update")
    # the ranges of v2, v3, v4 should have been squashed
    self.assertEqual(f2.sys_period.lower, v2.sys_period.lower)
    self.assertEqual(f2.sys_period.upper, v4.sys_period.upper)

    # but nothing else should avec changed.
    self.assertEqual(buildings_diff_fields(v2, f2), set(["event_type"]))


def insert_building_history_2():
    # simple case : just a building, no squashing, just an event update

    rnb_id = "BUILDING_2"
    b = Building.objects.create(
        rnb_id=rnb_id,
        point="POINT (3.702711216191982 49.30480507711158)",
        created_at="2023-12-11 04:00:35.005 +0100",
        updated_at="2023-12-11 04:00:35.005 +0100",
        shape="MULTIPOLYGON (((3.702622150150296 49.304784015647726, 3.702693383202145 49.3048663059031, 3.702798693694756 49.30482613857543, 3.702734346050333 49.30474470727255, 3.702622150150296 49.304784015647726)))",
        ext_ids='[{"id": "bdnb-bc-SSW2-CGZB-QYUT", "source": "bdnb", "created_at": "2023-12-09T23:01:05.518305+00:00", "source_version": "2023_01"}]',
        event_origin={"id": 151, "source": "import"},
        status="constructed",
        is_active=True,
    )
    return rnb_id


def assertions_for_building_2(self, initial_buildings, fixed_buildings):
    [v0] = initial_buildings
    [f0] = fixed_buildings

    # The event type should have been filled with "creation"
    self.assertEqual(f0.event_type, "creation")
    self.assertEqual(buildings_diff_fields(v0, f0), set(["event_type"]))


def insert_building_history_3():
    # typical case : building created by BDNB import, updated by BD TOPO

    rnb_id = "BUILDING_3"

    b = Building.objects.create(
        rnb_id=rnb_id,
        point="POINT (3.702711216191982 49.30480507711158)",
        created_at="2023-12-11 04:00:35.005 +0100",
        updated_at="2023-12-11 04:00:35.005 +0100",
        shape="MULTIPOLYGON (((3.702622150150296 49.304784015647726, 3.702693383202145 49.3048663059031, 3.702798693694756 49.30482613857543, 3.702734346050333 49.30474470727255, 3.702622150150296 49.304784015647726)))",
        ext_ids='[{"id": "bdnb-bc-SSW2-CGZB-QYUT", "source": "bdnb", "created_at": "2023-12-09T23:01:05.518305+00:00", "source_version": "2023_01"}]',
        event_origin={"id": 151, "source": "import"},
        status="constructed",
        is_active=True,
    )

    # update by BDTOPO
    b.ext_ids = [
        {
            "id": "bdnb-bc-SSW2-CGZB-QYUT",
            "source": "bdnb",
            "created_at": "2023-12-09T23:01:05.518305+00:00",
            "source_version": "2023_01",
        },
        {
            "id": "BATIMENT0000002291948531",
            "source": "bdtopo",
            "created_at": "2023-12-21T11:39:40.876407+00:00",
            "source_version": "bdtopo_2023_09",
        },
    ]
    b.event_origin = {"id": 248, "source": "import"}
    b.save()

    return rnb_id


def assertions_for_building_3(self, initial_buildings, fixed_buildings):
    # no squashing expected, juste some event_type filled
    [v0, v1] = initial_buildings
    [f0, f1] = fixed_buildings

    self.assertEqual(buildings_diff_fields(v0, f0), set(["event_type"]))
    self.assertEqual(f0.event_type, "creation")

    self.assertEqual(buildings_diff_fields(v1, f1), set(["event_type"]))
    self.assertEqual(f1.event_type, "update")


def insert_building_history_4():
    # do not touch rows if event_type is already filled
    rnb_id = "BUILDING_4"

    b = Building.objects.create(
        rnb_id=rnb_id,
        point="POINT (3.702711216191982 49.30480507711158)",
        created_at="2023-12-11 04:00:35.005 +0100",
        updated_at="2023-12-11 04:00:35.005 +0100",
        shape="MULTIPOLYGON (((3.702622150150296 49.304784015647726, 3.702693383202145 49.3048663059031, 3.702798693694756 49.30482613857543, 3.702734346050333 49.30474470727255, 3.702622150150296 49.304784015647726)))",
        ext_ids='[{"id": "bdnb-bc-SSW2-CGZB-QYUT", "source": "bdnb", "created_at": "2023-12-09T23:01:05.518305+00:00", "source_version": "2023_01"}]',
        event_origin={"id": 151, "source": "import"},
        status="constructed",
        is_active=True,
        event_type="creation",
    )

    b.event_type = "update"
    b.save()

    return rnb_id


def assertions_for_building_4(self, initial_buildings, fixed_buildings):
    # no squashing expected, no updates expected
    [v0, v1] = initial_buildings
    [f0, f1] = fixed_buildings

    self.assertEqual(buildings_diff_fields(v0, f0), set([]))

    self.assertEqual(buildings_diff_fields(v1, f1), set([]))


# todo : faire un test où un bâtiment doit avoir event_type complété pour ses premières lignes et a été modifié ensuite


def insert_building_history_5():
    # This is a merge case. We will have two buildings with missing event_type, then we merge them.
    # We will check the two parent and the child

    # ##########
    # Parent 1 is created as it would with a buggy import
    rnb_id_1 = "PARENT_1"
    parent_1 = Building.objects.create(
        rnb_id=rnb_id_1,
        point="POINT (3.702711216191982 49.30480507711158)",
        created_at="2023-12-11 04:00:35.005 +0100",
        updated_at="2023-12-11 04:00:35.005 +0100",
        shape="MULTIPOLYGON (((3.702622150150296 49.304784015647726, 3.702693383202145 49.3048663059031, 3.702798693694756 49.30482613857543, 3.702734346050333 49.30474470727255, 3.702622150150296 49.304784015647726)))",
        ext_ids=[
            {
                "id": "bdnb-bc-SSW2-CGZB-QYUT",
                "source": "bdnb",
                "created_at": "2023-12-09T23:01:05.518305+00:00",
                "source_version": "2023_01",
            }
        ],
        event_origin={"id": 151, "source": "import"},
        status="constructed",
        is_active=True,
    )

    # Then it is updated with a new ext_id and a new event_origin but without event_type
    new_ext_ids = [
        {
            "id": "bdnb-bc-SSW2-CGZB-QYUT",
            "source": "bdnb",
            "created_at": "2023-12-09T23:01:05.518305+00:00",
            "source_version": "2023_01",
        },
        {
            "id": "bdtopo_id",
            "source": "bdtopo",
            "created_at": "2023-12-09T23:01:05.518305+00:00",
            "source_version": "Q3_2024",
        },
    ]
    parent_1.ext_ids = new_ext_ids

    parent_1.event_origin = {"id": 152, "source": "import"}
    parent_1.save()

    # Then it is "updated" with the same data, still w/o event_type.
    parent_1.event_origin = {"id": 153, "source": "import"}

    # ##########
    # Parent 2 is created as it would with a buggy import
    rnb_id_2 = "PARENT_2"
    parent_2 = Building.objects.create(
        rnb_id=rnb_id_2,
        point="POINT (3.702711216191983 49.30480507711159)",
        created_at="2023-12-11 04:00:35.005 +0100",
        updated_at="2023-12-11 04:00:35.005 +0100",
        shape="MULTIPOLYGON (((3.702622150150296 49.304784015647726, 3.702693383202145 49.3048663059031, 3.702798693694756 49.30482613857543, 3.702734346050333 49.30474470727255, 3.702622150150296 49.304784015647726)))",
        ext_ids=[
            {
                "id": "bdnb_2",
                "source": "bdnb",
                "created_at": "2023-12-09T23:01:05.518305+00:00",
                "source_version": "2023_01",
            }
        ],
        event_origin={"id": 151, "source": "import"},
        status="constructed",
        is_active=True,
    )

    # Then it is "updated" with the same data, still w/o event_type.
    parent_2.event_origin = {"id": 153, "source": "import"}

    # ##########
    # The merge occurs
    user = User.objects.create_user(username="test_user", password="test_password")
    child = Building.merge(
        [parent_1, parent_2],
        user=user,
        event_origin={"dummy": "dummy"},
        status="constructed",
        addresses_id=[],
    )

    return child.rnb_id


class IdenticalBdgVersionsDetection(TestCase):
    def test_rnb_id_not_identical(self):
        b1 = Building(rnb_id="rnb_id_1")
        b2 = Building(rnb_id="rnb_id_2")
        self.assertEqual(buildings_diff_fields(b1, b2), set(["rnb_id"]))
        self.assertFalse(building_identicals(b1, b2))

    def test_rnb_id_identical(self):
        b1 = Building(rnb_id="rnb_id")
        b2 = Building(rnb_id="rnb_id")
        self.assertEqual(buildings_diff_fields(b1, b2), set([]))
        self.assertTrue(building_identicals(b1, b2))

    def test_point_not_identical(self):

        p1 = GEOSGeometry("POINT (3.702711216191982 49.30480507711158)")
        p2 = GEOSGeometry("POINT (3.702711216191982 49.30480507711157)")

        b1 = Building(point=p1)
        b2 = Building(point=p2)
        self.assertEqual(buildings_diff_fields(b1, b2), set(["point"]))
        self.assertFalse(building_identicals(b1, b2))

    def test_point_identical(self):

        p1 = GEOSGeometry("POINT (3.702711216191982 49.30480507711158)")
        p2 = GEOSGeometry("POINT (3.702711216191982 49.30480507711158)")

        b1 = Building(point=p1)
        b2 = Building(point=p2)
        self.assertEqual(buildings_diff_fields(b1, b2), set([]))
        self.assertTrue(building_identicals(b1, b2))

    def test_shape_not_identical(self):

        s1 = GEOSGeometry(
            "MULTIPOLYGON (((3.702622150150296 49.304784015647726, 3.702693383202145 49.3048663059031, 3.702798693694756 49.30482613857543, 3.702734346050333 49.30474470727255, 3.702622150150296 49.304784015647726)))"
        )
        s2 = GEOSGeometry(
            "POLYGON ((3.702622150150296 49.304784015647726, 3.702693383202145 49.3048663059031, 3.702798693694756 49.30482613857543, 3.702734346050333 49.30474470727255, 3.702622150150296 49.304784015647726))"
        )

        b1 = Building(shape=s1)
        b2 = Building(shape=s2)

        self.assertEqual(buildings_diff_fields(b1, b2), set(["shape"]))
        self.assertFalse(building_identicals(b1, b2))

    def test_shape_identical(self):
        s1 = GEOSGeometry(
            "MULTIPOLYGON (((3.702622150150296 49.304784015647726, 3.702693383202145 49.3048663059031, 3.702798693694756 49.30482613857543, 3.702734346050333 49.30474470727255, 3.702622150150296 49.304784015647726)))"
        )
        s2 = GEOSGeometry(
            "MULTIPOLYGON (((3.702622150150296 49.304784015647726, 3.702693383202145 49.3048663059031, 3.702798693694756 49.30482613857543, 3.702734346050333 49.30474470727255, 3.702622150150296 49.304784015647726)))"
        )

        b1 = Building(shape=s1)
        b2 = Building(shape=s2)

        self.assertEqual(buildings_diff_fields(b1, b2), set([]))
        self.assertTrue(building_identicals(b1, b2))

    def test_parents_not_identical(self):
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
        b1 = Building(is_active=True)
        b2 = Building(is_active=False)
        self.assertEqual(buildings_diff_fields(b1, b2), set(["is_active"]))
        self.assertFalse(building_identicals(b1, b2))

    def test_is_active_identical(self):

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

    def test_addresses_id_identical(self):

        # Same order
        b1 = Building(addresses_id=["id1", "id2"])
        b2 = Building(addresses_id=["id1", "id2"])
        self.assertEqual(buildings_diff_fields(b1, b2), set([]))
        self.assertTrue(building_identicals(b1, b2))

        # Different order
        b3 = Building(addresses_id=["id2", "id1"])
        self.assertEqual(buildings_diff_fields(b1, b3), set([]))
        self.assertTrue(building_identicals(b1, b3))

        # Both null
        b4 = Building(addresses_id=None)
        b5 = Building()
        self.assertEqual(buildings_diff_fields(b4, b5), set([]))
        self.assertTrue(building_identicals(b4, b5))

    def test_addresses_id_not_identical(self):

        b1 = Building(addresses_id=["id1", "id2"])
        b2 = Building(addresses_id=["id1", "id3"])
        self.assertEqual(buildings_diff_fields(b1, b2), set(["addresses_id"]))
        self.assertFalse(building_identicals(b1, b2))

        # One is empty
        b3 = Building(addresses_id=[])
        self.assertEqual(buildings_diff_fields(b1, b3), set(["addresses_id"]))
        self.assertFalse(building_identicals(b1, b3))

        # One is null
        b4 = Building(addresses_id=None)
        self.assertEqual(buildings_diff_fields(b1, b4), set(["addresses_id"]))
        self.assertFalse(building_identicals(b1, b4))

        # One has an extra address_id
        b5 = Building(addresses_id=["id1", "id2", "id3"])
        self.assertEqual(buildings_diff_fields(b1, b5), set(["addresses_id"]))
        self.assertFalse(building_identicals(b1, b5))

    def test_event_id_not_identical(self):

        b1 = Building(event_id="id1")
        b2 = Building(event_id="id2")
        self.assertEqual(buildings_diff_fields(b1, b2), set(["event_id"]))
        self.assertFalse(building_identicals(b1, b2))

    def test_event_id_identical(self):

        b1 = Building(event_id="id1")
        b2 = Building(event_id="id1")
        self.assertEqual(buildings_diff_fields(b1, b2), set([]))
        self.assertTrue(building_identicals(b1, b2))

    def test_event_type_not_identical(self):

        b1 = Building(event_type="type1")
        b2 = Building(event_type="type2")
        self.assertEqual(buildings_diff_fields(b1, b2), set(["event_type"]))
        self.assertFalse(building_identicals(b1, b2))

        # One is null
        b3 = Building(event_type=None)
        self.assertEqual(buildings_diff_fields(b1, b3), set(["event_type"]))
        self.assertFalse(building_identicals(b1, b3))
