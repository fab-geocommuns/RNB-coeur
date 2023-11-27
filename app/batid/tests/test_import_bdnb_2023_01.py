from datetime import datetime

from django.contrib.gis.geos import Point, MultiPolygon
from django.test import TransactionTestCase
from unittest.mock import patch

import batid.services.imports.import_bdnb_2023_01 as import_bdnb_2023_01
from batid.models import Candidate
from batid.tests import helpers


class ImportBDNB202301TestCase(TransactionTestCase):
    @patch("batid.services.imports.import_bdnb_2023_01.Source.find")
    def test_import_bdgs(self, sourceMock):
        sourceMock.return_value = helpers.fixture_path("bdnb_2023_01_bdgs.csv")

        # We check there are no candidates
        self.assertEqual(Candidate.objects.count(), 0)

        # Exec the import
        import_bdnb_2023_01.import_bdnd_2023_01_bdgs("38")

        # We check there are now 2 candidates (those in the csv)
        self.assertEqual(Candidate.objects.count(), 3)

        c = Candidate.objects.filter(source_id="bdnb-bc-1115-BJGL-HY7G").first()
        self.assertEqual(c.source, "bdnb")
        self.assertEqual(c.source_version, "2023.01")
        self.assertEqual(c.is_shape_fictive, False)
        self.assertEqual(c.is_light, False)
        self.assertListEqual(c.address_keys, ["38517_0345_00007"])
        self.assertDictEqual(c.created_by, {"source": "import", "id": 1})
        self.assertIsInstance(c.shape, MultiPolygon)
        self.assertIsInstance(c.created_at, datetime)
        self.assertIsInstance(c.created_at, datetime)

        c = Candidate.objects.filter(source_id="bdnb-bc-111D-RG76-V7GK").first()
        self.assertEqual(c.source, "bdnb")
        self.assertEqual(c.source_version, "2023.01")
        self.assertEqual(c.is_shape_fictive, False)
        self.assertEqual(c.is_light, False)
        self.assertListEqual(c.address_keys, ["38117_0153_02822", "38117_0153_02824"])
        self.assertDictEqual(c.created_by, {"source": "import", "id": 1})
        self.assertIsInstance(c.shape, MultiPolygon)
        self.assertIsInstance(c.created_at, datetime)
        self.assertIsInstance(c.created_at, datetime)

        c = Candidate.objects.filter(source_id="bdnb-bc-KCFS-ZDYC-D9D5").first()
        self.assertEqual(c.source, "bdnb")
        self.assertEqual(c.source_version, "2023.01")
        self.assertEqual(c.is_shape_fictive, True)
        self.assertEqual(c.is_light, False)
        self.assertListEqual(c.address_keys, [])
        self.assertDictEqual(c.created_by, {"source": "import", "id": 1})
        self.assertIsInstance(c.shape, MultiPolygon)
        self.assertIsInstance(c.created_at, datetime)
        self.assertIsInstance(c.created_at, datetime)

    def test_import_addresses(self):
        pass
