from django.test import TransactionTestCase

from batid.models import Address
from batid.models import Building
from batid.models import BuildingWithHistory
from batid.services.data_fix.fill_empty_event_origin import buildings_diff_fields
from batid.services.data_fix.fill_empty_event_origin import fix


class FixMissingEventOriginTest(TransactionTestCase):
    def test_fill_empty_event_origin(self):

        rnb_id_1 = insert_building_history_1()
        rnb_id_2 = insert_building_history_2()
        rnb_id_3 = insert_building_history_3()
        rnb_id_4 = insert_building_history_4()

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

        fix(1)

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

    # 1st update
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

    # 2nd update
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

    # 3rd update
    b.event_origin = {"id": 468, "source": "import"}
    b.save()

    # 4th update
    b.event_origin = {"id": 523, "source": "import"}
    b.save()

    return rnb_id


def assertions_for_building_1(self, initial_buildings, fixed_buildings):
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
