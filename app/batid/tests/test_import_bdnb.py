# we must use TransactionTestCase instead of TestCase because we are using raw SQL
# and are maually managing the transactions
# see https://docs.djangoproject.com/en/dev/topics/testing/tools/#transactiontestcase
from django.test import TransactionTestCase
from unittest.mock import patch
import batid.services.imports.import_bdnb7 as import_bdnb7
from batid.models import Address, Building, Candidate, BuildingImport
import batid.tests.helpers as helpers
from django.conf import settings
from batid.services.candidate import Inspector


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

    @patch("batid.services.imports.import_bdnb7.Source.find")
    def test_import_bdnb_buildings(self, sourceMock):
        sourceMock.side_effect = [
            helpers.fixture_path("rel_batiment_groupe_adresse.csv"),
            helpers.fixture_path("batiment_construction_bdnb.csv"),
            helpers.fixture_path("rel_batiment_groupe_adresse.csv"),
            helpers.fixture_path("batiment_construction_bdnb_update.csv"),
        ]

        # there are initially no buildings nor candidate
        self.assertEqual(Building.objects.count(), 0)
        self.assertEqual(Candidate.objects.count(), 0)

        # launch the import
        import_bdnb7.import_bdnb7_bdgs("33")

        # the fixture contains 4 buildings => 4 candidates
        # but no buildings are created
        self.assertEqual(Building.objects.count(), 0)
        self.assertEqual(Candidate.objects.count(), 4)

        # check the candidates are correctly imported
        candidates = Candidate.objects.all()

        addresses = ["01300_0013_00145", "3000000C051200101", "3000000C051200201"]

        candidate_1 = candidates[0]
        self.assertEqual(candidate_1.shape.srid, 4326)
        self.assertEqual(candidate_1.source, "bdnb")
        self.assertEqual(candidate_1.is_light, False)
        self.assertEqual(candidate_1.source_id, "BATIMENT0000000008834985-1")
        self.assertEqual(
            candidate_1.address_keys,
            addresses,
        )

        candidate_2 = candidates[1]
        self.assertEqual(candidate_2.shape.srid, 4326)
        self.assertEqual(candidate_2.source, "bdnb")
        self.assertEqual(candidate_2.is_light, False)
        self.assertEqual(candidate_2.source_id, "BATIMENT0000000008834991-1")
        # construction 0 and 1 are linked to the same building group
        # so they share the same addresses
        self.assertEqual(
            candidate_2.address_keys,
            addresses,
        )

        candidate_3 = candidates[2]
        self.assertEqual(candidate_3.shape.srid, 4326)
        self.assertEqual(candidate_3.source, "bdnb")
        self.assertEqual(candidate_3.is_light, False)
        self.assertEqual(candidate_3.source_id, "BATIMENT0000000008838153-1")
        # no address is linked to this building
        self.assertEqual(candidate_3.address_keys, [])
        self.assertEqual(candidate_3.is_shape_fictive, True)

        # test a building import has been recorded
        building_imports = BuildingImport.objects.all()

        self.assertEqual(len(building_imports), 1)
        building_import = building_imports[0]

        self.assertEqual(building_import.building_created_count, 0)
        self.assertEqual(building_import.building_refused_count, 0)
        self.assertEqual(building_import.building_updated_count, 0)
        self.assertEqual(building_import.candidate_created_count, 4)
        self.assertEqual(building_import.departement, "33")
        self.assertEqual(building_import.import_source, "bdnb_7")

        self.assertEqual(
            candidate_1.candidate_created_by,
            {"source": "import", "id": building_import.id},
        )
        self.assertEqual(
            candidate_2.candidate_created_by,
            {"source": "import", "id": building_import.id},
        )
        self.assertEqual(
            candidate_3.candidate_created_by,
            {"source": "import", "id": building_import.id},
        )

        # manually insert some addresses for foreign key constraints
        Address.objects.create(id="01300_0013_00145")
        Address.objects.create(id="3000000C051200101")
        Address.objects.create(id="3000000C051200201")

        # launch the inspector
        i = Inspector()
        i.inspect()

        buildings = Building.objects.all().order_by("created_at")
        self.assertEqual(len(buildings), 3)

        building_import.refresh_from_db()

        self.assertEqual(building_import.building_created_count, 3)
        self.assertEqual(building_import.building_updated_count, 0)
        # One candidate is refused because its area is too small
        self.assertEqual(building_import.building_refused_count, 1)


        buildings[0].refresh_from_db()
        self.assertEqual(buildings[0].last_updated_by, {"source": "import", "id": building_import.id})

        # launch a second import to test some building updates
        import_bdnb7.import_bdnb7_bdgs("33")

        # the fixture contains 1 building
        self.assertEqual(Candidate.objects.count(), 1)

        building_imports = BuildingImport.objects.all().order_by("-created_at")
        last_building_import = building_imports[0]

        self.assertEqual(last_building_import.building_created_count, 0)
        self.assertEqual(last_building_import.building_updated_count, 0)
        self.assertEqual(last_building_import.building_refused_count, 0)

        # launch the inspector
        i = Inspector()
        i.inspect()

        last_building_import.refresh_from_db()

        self.assertEqual(last_building_import.building_created_count, 0)
        self.assertEqual(last_building_import.building_updated_count, 1)
        self.assertEqual(last_building_import.building_refused_count, 0)

        buildings = Building.objects.all().order_by("created_at")
        
        self.assertEqual(buildings[0].ext_ids[0]["id"], "BATIMENT0000000008834985-1")
        self.assertEqual(buildings[0].ext_ids[1]["id"], "NOUVEL_ID")

        # we expect the last_updated_by field to be updated with the second import id
        self.assertEqual(buildings[0].last_updated_by, {"source": "import", "id": last_building_import.id})