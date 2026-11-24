from datetime import datetime
from unittest.mock import patch

from batid.models import Building, BuildingImport, Candidate
from batid.services.candidate import Inspector
from batid.services.imports import building_import_history
from batid.services.imports.import_bdtopo import (
    _transform_bdtopo_feature,
    bdtopo_dpts_list,
    bdtopo_src_params,
    create_bdtopo_full_import_tasks,
    create_candidate_from_bdtopo,
)
from batid.services.tchap import TchapLevel
from batid.tasks import convert_bdtopo
from batid.tests import helpers
from batid.tests.factories.users import UserFactory
from batid.tests.helpers import create_default_bdg
from django.contrib.gis.geos import GEOSGeometry, MultiPolygon
from django.db import OperationalError, connection, transaction
from django.test import TestCase, TransactionTestCase


class ImportBDTopoGeopackage(TransactionTestCase):
    def setUp(self):

        # RNB team user used by candidate.create_building_from_candidate()
        UserFactory(username="RNB")

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
        # BATIMENT0000000312141318 has a timestamp seconds set to 60 which is invalid but a common problem in bdtopo files. It should be skipped
        self.assertEqual(Candidate.objects.count(), 3)

        # Check the light bdtopo building is not imported
        c = Candidate.objects.filter(source_id="BATIMENT0000000312141366").first()
        self.assertIsNone(c)

        # Check, the already known building is not imported
        c = Candidate.objects.filter(source_id="BATIMENT0000000312141319").first()
        self.assertIsNone(c)

        # Check the "60s" timestamp bdtopo building is not imported
        c = Candidate.objects.filter(source_id="BATIMENT0000000312141318").first()
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

        # Expect 4 buildings: one from setUp and 3 from the import (candidate BATIMENT0000000312141318 should be rejected since it is too small)
        self.assertEqual(Building.objects.count(), 4)

    @patch("batid.services.imports.import_bdtopo._known_bdtopo_id")
    @patch("batid.services.imports.import_bdtopo.Source.find")
    @patch("batid.services.imports.import_bdtopo.Source.remove_uncompressed_folder")
    def test_convert_without_new_building(
        self, sourceRemoveFolderMock, sourceFindMock, knownBdtopoIdMock
    ):
        """
        Input: the fixture, every building of it already known in the RNB.
        Expected: no candidate, no error, the extracted folder removed.
        """
        sourceFindMock.return_value = helpers.fixture_path("bdtopo_for_test.gpkg")
        knownBdtopoIdMock.return_value = True

        create_candidate_from_bdtopo(bdtopo_src_params("02", "2025-09-15"))

        self.assertEqual(Candidate.objects.count(), 0)
        sourceRemoveFolderMock.assert_called_once()

    @patch("batid.services.imports.import_bdtopo.Source.find")
    @patch("batid.services.imports.import_bdtopo.Source.remove_uncompressed_folder")
    def test_replayed_convert_creates_no_duplicate(
        self, sourceRemoveFolderMock, sourceFindMock
    ):
        """
        Input: the fixture converted twice with the same bulk launch uuid (a Celery
        replay), then once with another uuid.
        Expected: 3 candidates and a single import row after the replay, 6
        candidates after the new launch.
        """
        sourceFindMock.return_value = helpers.fixture_path("bdtopo_for_test.gpkg")
        src_params = bdtopo_src_params("02", "2025-09-15")
        bulk_launch_uuid = "5f0c2d1e-8a3b-4c6d-9e7f-102938475600"

        create_candidate_from_bdtopo(src_params, bulk_launch_uuid)
        create_candidate_from_bdtopo(src_params, bulk_launch_uuid)
        self.assertEqual(Candidate.objects.count(), 3)
        building_import = BuildingImport.objects.get(bulk_launch_uuid=bulk_launch_uuid)
        self.assertEqual(building_import.candidate_created_count, 3)

        create_candidate_from_bdtopo(src_params, "7a1b2c3d-4e5f-4061-8293-a4b5c6d7e8f9")
        self.assertEqual(Candidate.objects.count(), 6)

    @patch(
        "batid.services.imports.import_bdtopo._known_bdtopo_id",
        side_effect=OperationalError("server closed the connection"),
    )
    @patch("batid.services.imports.import_bdtopo.Source.find")
    @patch("batid.services.imports.import_bdtopo.Source.remove_uncompressed_folder")
    def test_database_error_fails_the_conversion(
        self, sourceRemoveFolderMock, sourceFindMock, knownBdtopoIdMock
    ):
        """
        Input: the fixture, the lookup of known BD Topo ids raises a database error.
        Expected: the conversion raises the error and creates no candidate.
        """
        sourceFindMock.return_value = helpers.fixture_path("bdtopo_for_test.gpkg")

        with self.assertRaises(OperationalError):
            create_candidate_from_bdtopo(bdtopo_src_params("02", "2025-09-15"))

        self.assertEqual(Candidate.objects.count(), 0)

    @patch("batid.services.tchap.notify_tech")
    @patch(
        "batid.services.imports.import_bdtopo._known_bdtopo_id",
        side_effect=OperationalError("server closed the connection"),
    )
    @patch("batid.services.imports.import_bdtopo.Source.find")
    @patch("batid.services.imports.import_bdtopo.Source.remove_uncompressed_folder")
    def test_database_error_fails_the_task(
        self, sourceRemoveFolderMock, sourceFindMock, knownBdtopoIdMock, notifyMock
    ):
        """
        Input: convert_bdtopo (max_retries=3) on the fixture, the lookup of known BD
        Topo ids raising a database error on every attempt, run with .apply():
        Celery runs the retries eagerly, in the same call.
        Expected: 4 attempts, the task ends in FAILURE, no candidate; one failure
        message naming the task and its arguments, with the database error.
        """
        sourceFindMock.return_value = helpers.fixture_path("bdtopo_for_test.gpkg")

        result = convert_bdtopo.apply(args=[bdtopo_src_params("02", "2025-09-15")])

        self.assertEqual(result.state, "FAILURE")
        self.assertEqual(knownBdtopoIdMock.call_count, 4)
        self.assertEqual(Candidate.objects.count(), 0)
        notifyMock.assert_called_once_with(
            level=TchapLevel.FAILURE,
            title="Échec de la tâche",
            details=[
                ("Tâche", "batid.tasks.convert_bdtopo"),
                ("Identifiant", result.id),
                (
                    "Arguments",
                    "{'dpt': '002', 'projection': 'LAMB93', 'date': '2025-09-15'}",
                ),
            ],
            error="server closed the connection",
        )

    @patch("batid.services.imports.import_bdtopo._transform_bdtopo_feature")
    @patch("batid.services.imports.import_bdtopo.Source.find")
    @patch("batid.services.imports.import_bdtopo.Source.remove_uncompressed_folder")
    def test_skipped_features_are_counted(
        self, sourceRemoveFolderMock, sourceFindMock, transformMock
    ):
        """
        Input: the fixture, the transformation of BATIMENT0000000312141365 raises.
        Expected: the 2 other new buildings become candidates and the function
        returns 2 skipped features: that one and the one with an invalid date.
        """
        sourceFindMock.return_value = helpers.fixture_path("bdtopo_for_test.gpkg")

        def transform(feature, srid):
            if feature["properties"]["cleabs"] == "BATIMENT0000000312141365":
                raise Exception("broken geometry")
            return _transform_bdtopo_feature(feature, srid)

        transformMock.side_effect = transform

        skipped_count = create_candidate_from_bdtopo(
            bdtopo_src_params("02", "2025-09-15")
        )

        self.assertEqual(Candidate.objects.count(), 2)
        self.assertEqual(skipped_count, 2)


class TestImportTasks(TestCase):
    def test_tasks_count(self):
        """
        Input: every BD Topo department, release 2023-09-15.
        Expected: a chord whose header holds one 2-task chain per department and
        whose body is the summary task, with the launch uuid and the release date.
        """
        dpts = bdtopo_dpts_list()

        full_import = create_bdtopo_full_import_tasks(dpts, "2023-09-15")

        self.assertEqual(len(full_import.tasks), len(dpts))
        for dpt_chain in full_import.tasks:
            self.assertEqual(len(dpt_chain.tasks), 2)

        body = full_import.body
        self.assertEqual(body.task, "batid.tasks.report_bdtopo_import")
        self.assertEqual(body.kwargs["release_date"], "2023-09-15")
        launch_uuid = full_import.tasks[0].tasks[1].args[1]
        self.assertEqual(body.kwargs["bulk_launch_uuid"], str(launch_uuid))


class TestLockBuildingImport(TestCase):
    def test_lock_wait_is_not_cut_by_the_statement_timeout(self):
        """
        Input: the lock of a department import taken in a transaction, on a
        connection with a statement_timeout (15 s on the worker).
        Expected: the statement_timeout is 0 until the end of the transaction, so a
        run waiting for another one's COPY is not cancelled.
        """
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL statement_timeout = 15000")
            building_import_history.lock_building_import(
                source="bdtopo", bulk_launch_uuid="test", dpt="02"
            )
            with connection.cursor() as cursor:
                cursor.execute("SHOW statement_timeout")
                self.assertEqual(cursor.fetchone()[0], "0")
