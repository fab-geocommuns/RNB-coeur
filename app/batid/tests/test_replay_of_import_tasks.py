import gzip
import json
import os
import shutil
import tempfile
import uuid
from unittest.mock import patch

import batid.services.candidate as candidate_service
import batid.services.imports.import_plots as import_plots
import batid.tests.helpers as helpers
from batid.models import Address, Building, BuildingImport, Candidate, City, Plot
from batid.services.candidate import Inspector
from batid.services.imports.import_ban import import_ban_addresses
from batid.services.imports.import_cities import import_etalab_cities
from batid.services.imports.import_plots import import_etalab_plots
from batid.services.source import Source
from batid.tasks import dl_source
from batid.tests.factories.users import UserFactory
from batid.tests.helpers import coords_to_mp_geom, create_paris
from django.test import SimpleTestCase, TestCase


class WorkerKilled(Exception):
    """Stands for a worker killed by a deploy in the middle of a task."""


def _kill_on_call(*, target, attribute: str, call: int):
    """Patch target.attribute: its call-th call does its work, then the worker is
    killed (WorkerKilled is raised)."""
    original = getattr(target, attribute)
    calls = {"count": 0}

    def run_then_kill(*args, **kwargs):
        calls["count"] += 1
        result = original(*args, **kwargs)
        if calls["count"] == call:
            raise WorkerKilled()
        return result

    # On a class, autospec passes self to run_then_kill
    return patch.object(
        target,
        attribute,
        autospec=isinstance(target, type),
        side_effect=run_then_kill,
    )


@patch("batid.services.imports.import_ban.Source.find")
class TestReplayOfBanImport(TestCase):
    """acks_late: a task killed mid-run is redelivered and runs again from the
    start, on a database holding the batches the killed run already committed."""

    @staticmethod
    def _state() -> dict:
        return {
            a.cle_interop: (
                a.source,
                str(a.point),
                a.street_number,
                a.street_rep,
                a.street,
                a.city_name,
                a.city_zipcode,
                a.city_insee_code,
                a.ban_id,
            )
            for a in Address.objects.all()
        }

    def test_replay_gives_the_single_run_result(self, mock_find):
        """
        Input: the 4 addresses of the BAN file; an import with batch_size=1 killed
        after its 2nd batch, then a complete run of the same launch.
        Expected: same addresses as a single complete run, a single import history
        row for the launch.
        """
        mock_find.return_value = helpers.fixture_path("ban_with_ids_test_data.csv")
        import_ban_addresses({"dpt": "04"}, str(uuid.uuid4()), batch_size=1)
        single_run = self._state()
        Address.objects.all().delete()
        BuildingImport.objects.all().delete()

        bulk_launch_uuid = str(uuid.uuid4())
        with _kill_on_call(target=Address.objects, attribute="bulk_create", call=2):
            with self.assertRaises(WorkerKilled):
                import_ban_addresses({"dpt": "04"}, bulk_launch_uuid, batch_size=1)
        import_ban_addresses({"dpt": "04"}, bulk_launch_uuid, batch_size=1)

        self.assertEqual(len(single_run), 4)
        self.assertEqual(self._state(), single_run)
        self.assertEqual(
            BuildingImport.objects.filter(bulk_launch_uuid=bulk_launch_uuid).count(),
            1,
        )


@patch("batid.services.imports.import_plots.remove_after_task_success")
@patch("batid.services.imports.import_plots.Source")
class TestReplayOfPlotsImport(TestCase):
    @staticmethod
    def _state() -> dict:
        return {p.id: (str(p.shape), p.source_version) for p in Plot.objects.all()}

    def test_replay_gives_the_single_run_result(self, mock_source, _mock_remove):
        """
        Input: the 3 plots of the cadastre file; an import with batch_size=1 killed
        after its 2nd batch, then a complete run.
        Expected: the killed run leaves no plot (one transaction), the replay gives
        the same plots as a single complete run.
        """
        mock_source.return_value.path = helpers.fixture_path(
            "cadastre_extract_data.json"
        )
        import_etalab_plots("38", "2024-12-13", 1)
        single_run = self._state()
        Plot.objects.all().delete()

        with _kill_on_call(
            target=import_plots,
            attribute="_save_plots",
            call=2,
        ):
            with self.assertRaises(WorkerKilled):
                import_etalab_plots("38", "2024-12-13", 1)
        self.assertEqual(Plot.objects.count(), 0)
        import_etalab_plots("38", "2024-12-13", 1)

        self.assertEqual(len(single_run), 3)
        self.assertEqual(self._state(), single_run)


@patch("batid.services.imports.import_cities.fetch_dpt_cities_geojson")
class TestReplayOfCitiesImport(TestCase):
    @staticmethod
    def _state() -> dict:
        return {c.code_insee: (c.name, str(c.shape)) for c in City.objects.all()}

    def test_replay_gives_the_single_run_result(self, mock_fetch):
        """
        Input: the cities of the department file; an import killed after its 2nd
        city, then a complete run.
        Expected: same cities as a single complete run.
        """
        with open(helpers.fixture_path("cities.geojson")) as f:
            mock_fetch.return_value = json.load(f)
        import_etalab_cities("33")
        single_run = self._state()
        City.objects.all().delete()

        with _kill_on_call(target=City.objects, attribute="update_or_create", call=2):
            with self.assertRaises(WorkerKilled):
                import_etalab_cities("33")
        import_etalab_cities("33")

        self.assertEqual(len(single_run), 2)
        self.assertEqual(self._state(), single_run)


class TestReplayOfInspection(TestCase):
    COORDS = [
        [2.349804906833981, 48.85789205519228],
        [2.349701279442314, 48.85786369735885],
        [2.3496535925009994, 48.85777922711969],
        [2.349861764341199, 48.85773095834841],
        [2.3499452164882086, 48.857847406681174],
        [2.349804906833981, 48.85789205519228],
    ]

    def setUp(self):
        UserFactory(username="RNB")
        create_paris()

    def _create_candidates(self):
        # 3 candidates about 70 m apart: each one creates its own building
        for i in range(3):
            Candidate.objects.create(
                shape=coords_to_mp_geom(
                    [[lng + i * 0.001, lat] for lng, lat in self.COORDS]
                ),
                source="bdtopo",
                source_version="2026-09-15",
                source_id=f"bdtopo_{i}",
                address_keys=[],
                is_light=False,
                created_by={"id": 1, "source": "import"},
            )

    def test_replay_creates_each_building_once(self):
        """
        Input: 3 candidates far from any building; an inspection killed in the
        middle of its 2nd candidate, once its building is created and before the
        candidate is saved, then a complete run.
        Expected: the 3 candidates decided "creation", 3 buildings in all, one per
        candidate shape, each referencing its candidate once.
        """
        self._create_candidates()
        with _kill_on_call(
            target=candidate_service, attribute="create_building_from_candidate", call=2
        ):
            with self.assertRaises(WorkerKilled):
                Inspector().inspect()
        Inspector().inspect()

        candidates = Candidate.objects.order_by("source_id")
        self.assertEqual(
            [c.inspection_details["decision"] for c in candidates],
            ["creation"] * 3,
        )
        self.assertEqual(Building.objects.count(), 3)
        for candidate in candidates:
            building = Building.objects.get(
                rnb_id=candidate.inspection_details["rnb_id"]
            )
            self.assertTrue(building.shape.equals(candidate.shape))
            self.assertEqual([e["id"] for e in building.ext_ids], [candidate.source_id])


class TestReplayOfDownload(SimpleTestCase):
    CONTENT = b"id;lon;lat\n1;2.35;48.85\n"

    def setUp(self):
        self.dl_dir = tempfile.mkdtemp()
        patcher = patch.object(Source, "_dl_dir", self.dl_dir)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(shutil.rmtree, self.dl_dir)

    def _files(self) -> dict:
        files = {}
        for root, _dirs, names in os.walk(self.dl_dir):
            for name in names:
                path = os.path.join(root, name)
                with open(path, "rb") as f:
                    files[os.path.relpath(path, self.dl_dir)] = f.read()
        return files

    @patch("batid.services.source.requests.get")
    def test_replay_gives_the_single_run_result(self, mock_get):
        """
        Input: a BAN file download killed after its decompression, before the
        archive removal, then a complete run.
        Expected: same files as a single complete run: the decompressed file
        only, no archive and nothing left aside.
        """
        mock_get.return_value.content = gzip.compress(self.CONTENT)
        dl_source("ban_with_ids", {"dpt": "04"})
        single_run = self._files()
        shutil.rmtree(self.dl_dir)
        os.makedirs(self.dl_dir)

        with patch.object(Source, "remove_archive", side_effect=WorkerKilled()):
            with self.assertRaises(WorkerKilled):
                dl_source("ban_with_ids", {"dpt": "04"})
        dl_source("ban_with_ids", {"dpt": "04"})

        self.assertEqual(list(single_run.values()), [self.CONTENT])
        self.assertEqual(self._files(), single_run)
