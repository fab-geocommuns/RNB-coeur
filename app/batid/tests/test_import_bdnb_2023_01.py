from datetime import datetime
from unittest.mock import patch

from django.contrib.gis.geos import MultiPolygon
from django.contrib.gis.geos import Point
from django.test import TransactionTestCase

import batid.services.imports.import_bdnb_2023_01 as import_bdnb_2023_01
from batid.models import Address
from batid.models import Building
from batid.models import Candidate
from batid.services.candidate import Inspector
from batid.tests import helpers


class ImportBDNB202301TestCase(TransactionTestCase):
    @patch("batid.services.imports.import_bdnb_2023_01.Source.find")
    def test_import_bdgs(self, sourceMock):
        sourceMock.return_value = helpers.fixture_path("bdnb_2023_01_bdgs.csv")

        # ############
        # File to candidates
        # ############

        # We check there are no candidates
        self.assertEqual(Candidate.objects.count(), 0)

        # Exec the import
        import_bdnb_2023_01.import_bdnd_2023_01_bdgs("38")

        # We check there are now 2 candidates (those in the csv)
        self.assertEqual(Candidate.objects.count(), 3)

        c = Candidate.objects.filter(source_id="bdnb-bc-1115-BJGL-HY7G").first()
        self.assertEqual(c.source, "bdnb")
        self.assertEqual(c.source_version, "2023_01")
        self.assertEqual(c.is_light, False)
        self.assertListEqual(c.address_keys, ["38517_0345_00007"])
        self.assertIsInstance(c.created_by, dict)
        self.assertEqual(c.created_by["source"], "import")
        self.assertIsInstance(c.created_by["id"], int)
        self.assertIsInstance(c.created_by, dict)
        self.assertEqual(c.created_by["source"], "import")
        self.assertIsInstance(c.created_by["id"], int)
        self.assertIsInstance(c.shape, MultiPolygon)
        self.assertIsInstance(c.created_at, datetime)
        self.assertIsInstance(c.created_at, datetime)
        self.assertIsInstance(c.random, int)

        c = Candidate.objects.filter(source_id="bdnb-bc-111D-RG76-V7GK").first()
        self.assertEqual(c.source, "bdnb")
        self.assertEqual(c.source_version, "2023_01")
        self.assertEqual(c.is_light, False)
        self.assertListEqual(c.address_keys, ["38117_0153_02822", "38117_0153_02824"])
        self.assertIsInstance(c.created_by, dict)
        self.assertEqual(c.created_by["source"], "import")
        self.assertIsInstance(c.created_by["id"], int)
        self.assertIsInstance(c.shape, MultiPolygon)
        self.assertIsInstance(c.created_at, datetime)
        self.assertIsInstance(c.created_at, datetime)

        c = Candidate.objects.filter(source_id="bdnb-bc-KCFS-ZDYC-D9D5").first()
        self.assertEqual(c.source, "bdnb")
        self.assertEqual(c.source_version, "2023_01")
        self.assertIsInstance(c.shape, Point)
        self.assertEqual(c.is_light, False)
        self.assertListEqual(c.address_keys, [])
        self.assertIsInstance(c.created_by, dict)
        self.assertEqual(c.created_by["source"], "import")
        self.assertIsInstance(c.created_by["id"], int)
        # The shape is a point because the building is fictive in the fixture.
        self.assertIsInstance(c.shape, Point)
        self.assertIsInstance(c.created_at, datetime)
        self.assertIsInstance(c.created_at, datetime)

        # We create empty addresses
        Address.objects.create(id="38517_0345_00007")
        Address.objects.create(id="38117_0153_02822")
        Address.objects.create(id="38117_0153_02824")

        # ############
        # Candidates to files
        # ############

        self.assertEqual(Building.objects.count(), 0)

        i = Inspector()
        i.inspect()

        self.assertEqual(Building.objects.count(), 3)

        b = Building.objects.filter(
            ext_ids__contains=[{"id": "bdnb-bc-1115-BJGL-HY7G"}]
        ).first()
        self.assertEqual(len(b.ext_ids), 1)
        self.assertEqual(b.ext_ids[0]["source"], "bdnb")
        self.assertEqual(b.ext_ids[0]["source_version"], "2023_01")
        self.assertIsInstance(b.shape, MultiPolygon)
        self.assertIsInstance(b.point, Point)
        self.assertEqual(len(b.addresses_id), 1)

        b = Building.objects.filter(
            ext_ids__contains=[{"id": "bdnb-bc-111D-RG76-V7GK"}]
        ).first()
        self.assertEqual(len(b.ext_ids), 1)
        self.assertEqual(b.ext_ids[0]["source"], "bdnb")
        self.assertEqual(b.ext_ids[0]["source_version"], "2023_01")
        self.assertIsInstance(b.shape, MultiPolygon)
        self.assertIsInstance(b.point, Point)
        self.assertEqual(len(b.addresses_id), 2)

        b = Building.objects.filter(
            ext_ids__contains=[{"id": "bdnb-bc-KCFS-ZDYC-D9D5"}]
        ).first()
        self.assertEqual(len(b.ext_ids), 1)
        self.assertEqual(b.ext_ids[0]["source"], "bdnb")
        self.assertEqual(b.ext_ids[0]["source_version"], "2023_01")
        self.assertIsInstance(b.shape, Point)
        self.assertIsInstance(b.point, Point)
        self.assertEqual(len(b.addresses_id), 0)

    @patch("batid.services.imports.import_bdnb_2023_01.Source.find")
    def test_import_addresses(self, sourceMock):
        sourceMock.return_value = helpers.fixture_path("bdnb_2023_01_addresses.csv")

        self.assertEqual(Address.objects.count(), 0)

        import_bdnb_2023_01.import_bdnd_2023_01_addresses("38")

        self.assertEqual(Address.objects.count(), 3)

        a = Address.objects.get(id="38517_0345_00007")
        self.assertEqual(a.street_number, "7")
        self.assertEqual(a.street_rep, "")
        self.assertEqual(a.street_type, "place")
        self.assertEqual(a.street_name, "jean jaures")
        self.assertEqual(a.city_name, "Tullins")
        self.assertEqual(a.city_insee_code, "38517")
        self.assertEqual(a.city_zipcode, "38210")
        self.assertIsInstance(a.point, Point)

        # There is a duplicate address in the fixture. It should be imported once (without conflict)
        addresses = Address.objects.filter(id="38117_0153_02824")
        self.assertEqual(addresses.count(), 1)
