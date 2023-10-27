# we must use TransactionTestCase instead of TestCase because we are using raw SQL
# and are maually managing the transactions
# see https://docs.djangoproject.com/en/dev/topics/testing/tools/#transactiontestcase
from django.test import TransactionTestCase
from unittest.mock import patch
import batid.services.imports.import_bdnb7 as import_bdnb7
from batid.models import Address
import batid.tests.helpers as helpers


class ImportBDNBTestCase(TransactionTestCase):
    @patch("batid.services.imports.import_bdnb7.Source.find")
    def test_import_bdnb_addresses(self, sourceMock):
        sourceMock.return_value = helpers.fixture_path("adresses_bdnb.csv")

        # there are initially no addresses
        self.assertEqual(Address.objects.count(), 0)

        # launch the import
        import_bdnb7.import_bdnb7_addresses("33")

        # the fixture contains 4 addresses, but one is a duplicate
        self.assertEqual(Address.objects.count(), 3)

        # check the addresses are correctly imported
        address_1 = Address.objects.get(id="0010000A032800101")
        self.assertEqual(address_1.source, "Arcep")
        self.assertEqual(address_1.street_number, "9")
        self.assertEqual(address_1.street_rep, "B")
        self.assertEqual(address_1.street_name, "des 5 chemins")
        self.assertEqual(address_1.street_type, "rue")
        self.assertEqual(address_1.city_name, "L'Abergement-Clémenciat")
        self.assertEqual(address_1.city_zipcode, "01002")
        self.assertEqual(address_1.city_insee_code, "01001")
