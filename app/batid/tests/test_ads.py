from django.test import TestCase
from batid.tests.helpers import create_default_bdg, create_grenoble
from batid.models import ADS, BuildingADS, Signal


class ADSTestCase(TestCase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.city = None
        self.ads = None
        self.bdg = None

    def setUp(self):
        self.city = create_grenoble()
        self.ads = self._create_ads()
        self.bdg = create_default_bdg()

    def test_bdg_ads_signal(self):
        BuildingADS.objects.create(building=self.bdg, ads=self.ads, operation="build")
        # test the signal has been created
        signals = Signal.objects.filter(building=self.bdg, type="willBeBuilt")
        self.assertEqual(len(signals), 1)

        # test the signal has the right data
        s = signals.first()
        self.assertEqual(s.type, "willBeBuilt")
        self.assertEqual(s.building, self.bdg)
        self.assertEqual(s.origin, f"ADS:{self.ads.id}")
        self.assertEqual(s.creator_copy_id, None)
        self.assertEqual(s.creator_copy_fname, None)
        self.assertEqual(s.creator_copy_lname, None)
        self.assertEqual(s.creator_org_copy_id, None)
        self.assertEqual(s.creator_org_copy_name, None)

    def _create_ads(self):
        return ADS.objects.create(
            city=self.city, file_number="GOGO", decided_at="2020-01-01"
        )
