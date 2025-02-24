from django.contrib.gis.geos import MultiPolygon
from django.contrib.gis.geos import Polygon
from django.test import TestCase

from batid.models import Address
from batid.models import Building
from batid.services.imports.import_bal import create_bal_dpt_import_tasks
from batid.services.imports.import_bal import create_bal_full_import_tasks


class TestBALImport(TestCase):
    def setUp(self):
        # Create test data
        self.test_building = Building.objects.create(
            rnb_id="TEST123",
            shape=MultiPolygon(Polygon(((0, 0), (0, 1), (1, 1), (1, 0), (0, 0)))),
            is_active=True,
        )
        self.test_address = Address.objects.create(
            city_name="Paris", street="Rue de Test", street_number="42"
        )
        self.test_building.addresses_read_only.add(self.test_address)

    def test_create_bal_full_import_tasks(self):
        dpt_list = ["75", "92"]
        tasks = create_bal_full_import_tasks(dpt_list)

        assert len(tasks) == 4

    def test_create_bal_dpt_import_tasks(self):
        tasks = create_bal_dpt_import_tasks("75")

        assert len(tasks) == 2
        assert tasks[0].task == "batid.tasks.dl_source"
        assert tasks[1].task == "batid.tasks.convert_bal"
