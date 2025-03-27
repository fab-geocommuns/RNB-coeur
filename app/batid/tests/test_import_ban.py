from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch
from django.test import TestCase
from django.contrib.gis.geos import Point
from django.conf import settings


import batid.tests.helpers as helpers
from batid.models import Address
from batid.services.imports.import_ban import import_ban_addresses


class BANImportDB(TestCase):

    @patch("batid.services.imports.import_ban.Source.find")
    def test_import_on_empty_db_one_batch(self, sourceMock):
        sourceMock.return_value = helpers.fixture_path("ban_import_test_data.csv")

        self.assertEqual(Address.objects.count(), 0)

        # Now UTC time
        before_import = datetime.now(ZoneInfo(settings.TIME_ZONE))

        import_ban_addresses({"dpt": "dummy"}, batch_size=100)

        self.assertEqual(Address.objects.count(), 50)

        # Verify the first address
        address = Address.objects.get(id="04001_pk624e_00001")

        self.assertEqual(address.source, "Import BAN")
        self.assertEqual(address.point, Point(6.135212, 44.070028, srid=4326))
        self.assertEqual(address.street_number, "1")
        self.assertEqual(address.street_rep, "bis")
        self.assertEqual(address.street, "Impasse de la Treille")
        self.assertEqual(address.city_name, "Aiglun")
        self.assertEqual(address.city_zipcode, "04510")
        self.assertEqual(address.city_insee_code, "04001")
        self.assertGreater(address.created_at, before_import)
        self.assertGreater(address.updated_at, before_import)

    @patch("batid.services.imports.import_ban.Source.find")
    def test_import_on_empty_db_many_batches(self, sourceMock):
        sourceMock.return_value = helpers.fixture_path("ban_import_test_data.csv")

        self.assertEqual(Address.objects.count(), 0)

        import_ban_addresses({"dpt": "dummy"}, batch_size=1)

        self.assertEqual(Address.objects.count(), 50)

    @patch("batid.services.imports.import_ban.Source.find")
    def test_import_with_existing_addresses(self, sourceMock):
        sourceMock.return_value = helpers.fixture_path("ban_import_test_data.csv")

        # Create some addresse before import
        existing_address = Address.objects.create(
            id="04001_pk624e_00001",
            source="OldAddress",
            point=Point(0, 0, srid=4326),
            street_number="old_number",
            street_rep="old_rep",
            street="old_street",
            city_name="old_city",
            city_zipcode="00000",
            city_insee_code="11111",
        )
        old_created_at = existing_address.created_at
        old_updated_at = existing_address.updated_at

        self.assertEqual(Address.objects.count(), 1)

        import_ban_addresses({"dpt": "dummy"}, batch_size=100)

        self.assertEqual(Address.objects.count(), 50)

        # We verify the existing address has not been modified at all
        address = Address.objects.get(id="04001_pk624e_00001")

        self.assertEqual(address.source, "OldAddress")
        self.assertEqual(address.point, Point(0, 0, srid=4326))
        self.assertEqual(address.street_number, "old_number")
        self.assertEqual(address.street_rep, "old_rep")
        self.assertEqual(address.street, "old_street")
        self.assertEqual(address.city_name, "old_city")
        self.assertEqual(address.city_zipcode, "00000")
        self.assertEqual(address.city_insee_code, "11111")
        self.assertEqual(address.created_at, old_created_at)
        self.assertEqual(address.updated_at, old_updated_at)
