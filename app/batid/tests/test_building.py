from django.test import TestCase

from batid.models import Building
from batid.services.bdg_status import BuildingStatus
from batid.services.building import get_real_bdgs_queryset
from batid.services.rnb_id import generate_rnb_id


class Buildings(TestCase):
    def setUp(self):

        all_status = BuildingStatus.ALL_TYPES_KEYS

        for status in all_status:

            # Create an active building
            Building.objects.create(
                rnb_id=generate_rnb_id(),
                status=status,
                is_active=True,
            )

            # Create an inactive building
            Building.objects.create(
                rnb_id=generate_rnb_id(),
                status=status,
                is_active=False,
            )

    def test(self):

        bdgs = Building.objects.all().count()
        self.assertEqual(bdgs, 14)

        real_bdgs = get_real_bdgs_queryset()
        self.assertEqual(real_bdgs.count(), 4)

        real_status = [bdg.status for bdg in real_bdgs]
        self.assertEqual(set(real_status), set(BuildingStatus.REAL_BUILDINGS_STATUS))

        real_is_active = [bdg.is_active for bdg in real_bdgs]
        self.assertListEqual(real_is_active, [True] * 4)
