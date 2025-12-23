from datetime import datetime
from unittest.mock import patch

from django.contrib.gis.geos import GEOSGeometry
from django.contrib.gis.geos import Polygon, MultiPolygon
from django.test import TestCase
from django.test import TransactionTestCase

from batid.models import Building
from batid.models import Candidate
from batid.services.candidate import Inspector
from batid.services.imports.import_bdtopo import bdtopo_dpts_list
from batid.services.imports.import_bdtopo import bdtopo_src_params
from batid.services.imports.import_bdtopo import create_bdtopo_full_import_tasks
from batid.services.imports.import_bdtopo import create_candidate_from_bdtopo
from batid.services.source import Source
from batid.tests import helpers
from batid.tests.helpers import create_default_bdg


class ImportBDTopoGeopackage(TransactionTestCase):

    def setUp(self):

        # Create a bdg with a bdtopo ID also present in the file. It should be skipped
        bdg = create_default_bdg("RNB_ID")
        bdg.ext_ids = Building.add_ext_id(
            bdg.ext_ids,
            "bdtopo",
            "2025-09-15",
            "BATIMENT0000000312141319",
            "2025-12-15",
        )
        bdg.save()

    @patch("batid.services.imports.import_bdtopo.Source.find")
    @patch("batid.services.imports.import_bdtopo.Source.remove_uncompressed_folder")
    def test_convert(self, sourceRemoveFolderMock, sourceFindMock):

        sourceFindMock.return_value = helpers.fixture_path("bdtopo_for_test.gpkg")
        sourceRemoveFolderMock.return_value = None

        src_params = bdtopo_src_params("02", "2025-09-15")

        create_candidate_from_bdtopo(src_params)

        # The fixture file has 6 buildings
        # One of them is skipped because the database contains a bdg with the same bdtopo ID
        # Another one is skipped because it is a light building
        self.assertEqual(Candidate.objects.count(), 4)

        # Check the light bdtopo building is not imported
        c = Candidate.objects.filter(source_id="BATIMENT0000000312141366").first()
        self.assertIsNone(c)

        # Check, the already known building is not imported
        c = Candidate.objects.filter(source_id="BATIMENT0000000312141319").first()
        self.assertIsNone(c)

        # Check one of the imported buildings
        c = Candidate.objects.filter(source_id="BATIMENT0000000312141365").first()

        self.assertEqual(c.source, "bdtopo")
        self.assertEqual(c.source_version, "2025-09-15")
        self.assertEqual(c.is_light, False)
        self.assertListEqual(c.address_keys, [])
        self.assertIsInstance(c.created_by, dict)
        self.assertEqual(c.created_by["source"], "import")
        self.assertIsInstance(c.created_by["id"], int)
        self.assertIsInstance(c.shape, MultiPolygon)
        self.assertEqual(c.shape.srid, 4326)
        self.assertEqual(c.shape.dims, 2)  # We verify the 3D shape became a 2D shape
        self.assertIsInstance(c.created_at, datetime)
        self.assertIsInstance(c.random, int)

        refshape = GEOSGeometry(
            '{ "type": "MultiPolygon", "coordinates": [ [ [ [ 765634.199999999953434, 6971001.099999999627471, 181.6 ], [ 765626.599999999976717, 6970998.799999999813735, 181.6 ], [ 765620.300000000046566, 6970997.200000000186265, 181.6 ], [ 765620.599999999976717, 6970988.5, 181.6 ], [ 765625.599999999976717, 6970988.200000000186265, 181.6 ], [ 765625.400000000023283, 6970989.900000000372529, 181.6 ], [ 765633.800000000046566, 6970991.900000000372529, 181.6 ], [ 765633.0, 6970996.0, 181.6 ], [ 765635.0, 6970996.5, 181.6 ], [ 765634.199999999953434, 6971001.099999999627471, 181.6 ] ] ] ] }'
        )
        refshape.srid = 2154
        refshape.transform(4326)

        intersection = c.shape.intersection(refshape)
        self.assertEqual(round(intersection.area, 6), round(refshape.area, 6))

        i = Inspector()
        i.inspect()

        # Expect 4 buildings: one frome setUp and 3 from the import (candidate BATIMENT0000000312141318 should be rejected since it is too small)
        self.assertEqual(Building.objects.count(), 4)


class TestImportTasks(TestCase):
    def test_tasks_count(self):

        dpts = bdtopo_dpts_list()

        all_tasks = create_bdtopo_full_import_tasks(dpts, "2023-09-15")

        self.assertEqual(len(all_tasks), len(dpts))

        for dpt_chain in all_tasks:

            self.assertEqual(len(dpt_chain.tasks), 2)
