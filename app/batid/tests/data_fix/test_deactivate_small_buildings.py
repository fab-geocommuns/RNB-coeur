from django.contrib.auth.models import User
from django.test import TestCase

from batid.models.building import Building
from batid.models.others import DataFix, SummerChallenge
from batid.services.data_fix.deactivate_small_buildings import (
    deactivate_small_buildings,
)
from batid.tests.helpers import coords_to_mp_geom
from batid.tests.helpers import coords_to_point_geom


class TestDeactivateSmallBuildings(TestCase):
    def setUp(self):

        # Should be deactivated (area < MIN_BUILDING_AREA)
        too_small_coords = [
            [1.3700879356348707, 46.13019858165205],
            [1.3700879356348707, 46.1301961444135],
            [1.3700925345636392, 46.1301961444135],
            [1.3700925345636392, 46.13019858165205],
            [1.3700879356348707, 46.13019858165205],
        ]
        Building.objects.create(
            rnb_id="TOO_SMALL",
            shape=coords_to_mp_geom(too_small_coords),
            is_active=True,
        )

        # Should remain deactivated
        Building.objects.create(
            rnb_id="MINIINACTIVE",
            shape=coords_to_mp_geom(too_small_coords),
            is_active=False,
        )

        # Point building, should not be deactivated
        Building.objects.create(
            rnb_id="POINTBDG",
            is_active=True,
            shape=coords_to_point_geom(1.3700879356348707, 46.13019858165205),
        )

        # Big building, should not be deactivated
        big_building_coords = [
            [1.6484649736609356, 48.337562552017204],
            [1.650329345250526, 48.33649089024479],
            [1.6525446573743636, 48.33791247751353],
            [1.6500222722831666, 48.339501692249456],
            [1.6483662716356946, 48.33851026134636],
            [1.6491778216219188, 48.338138469786344],
            [1.6484649736609356, 48.337562552017204],
        ]
        Building.objects.create(
            rnb_id="BIGBDG",
            shape=coords_to_mp_geom(big_building_coords),
            is_active=True,
        )

        # 5,29 square meters, should not be deactivated
        justenough_building_coords = [
            [1.6455690602908248, 48.33938975828704],
            [1.6455995079779768, 48.33938086535184],
            [1.6456121945149107, 48.33939665797706],
            [1.6455782868627011, 48.339407237499984],
            [1.6455690602908248, 48.33938975828704],
        ]
        Building.objects.create(
            rnb_id="JUSTENOUGH",
            shape=coords_to_mp_geom(justenough_building_coords),
            is_active=True,
        )

        # 4,22 square meters, should be deactivated
        not_enough_building_coords = [
            [1.6456151931500926, 48.33939573801845],
            [1.6456034292716595, 48.3393800987194],
            [1.6456299556651004, 48.33937074580302],
            [1.64563733692259, 48.33938500516669],
            [1.6456327236366235, 48.339386385104916],
            [1.6456357222731413, 48.339391904857365],
            [1.6456151931500926, 48.33939573801845],
        ]
        Building.objects.create(
            rnb_id="TOO_SMALL_2",
            shape=coords_to_mp_geom(not_enough_building_coords),
            is_active=True,
        )

    def test(self):

        user = User.objects.create_user(username="tester")
        datafix = DataFix.objects.create(
            user=user, text="Désactiver les petits bâtiments importés par erreur"
        )

        # Count active/inactive buildings before
        active_count = Building.objects.filter(is_active=True).count()
        inactivate_count = Building.objects.filter(is_active=False).count()
        self.assertEqual(active_count, 5)
        self.assertEqual(inactivate_count, 1)

        # Run the data fix
        deactivated_count = deactivate_small_buildings(datafix.id, batch_size=2)
        self.assertEqual(deactivated_count, 2)

        # Verify active buildings after

        expected_active = ["POINTBDG", "BIGBDG", "JUSTENOUGH"]

        active_count = Building.objects.filter(is_active=True).count()
        self.assertEqual(active_count, len(expected_active))

        for rnb_id in expected_active:
            b = Building.objects.get(rnb_id=rnb_id)
            self.assertEqual(b.is_active, True, f"Building {rnb_id} should be active")

        # Verify inactive buildings after

        expected_inactive = ["TOO_SMALL", "MINIINACTIVE", "TOO_SMALL_2"]

        inactivate_count = Building.objects.filter(is_active=False).count()
        self.assertEqual(inactivate_count, len(expected_inactive))

        for rnb_id in expected_inactive:
            b = Building.objects.get(rnb_id=rnb_id)
            self.assertEqual(
                b.is_active, False, f"Building {rnb_id} should be inactive"
            )

        scores_count = SummerChallenge.objects.all().count()
        self.assertEqual(scores_count, 0)
