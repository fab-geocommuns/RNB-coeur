from audioop import add
from django.test import TestCase
from batid.models import Building, Address
from django.contrib.gis.geos import GEOSGeometry
import json
from batid.services.data_gouv_publication import create_rnb_csv_files, create_archive, cleanup_directory
import os

def get_geom():
    coords = {
        "coordinates": [
            [
                [2.6000591402070654, 48.814763140563656],
                [2.599867663762808, 48.814565787565414],
                [2.600525343722012, 48.8144177723068],
                [2.600708495117374, 48.81477684560585],
                [2.600367167550303, 48.81493074787656],
                [2.6000591402070654, 48.814763140563656],
            ]
        ],
        "type": "MultiPolygon",
    }

    return GEOSGeometry(json.dumps(coords), srid=4326)


class TestDataGouvPublication(TestCase):
    def test_create_rnb_csv_files(self):
        geom = get_geom()
        address = Address.objects.create(
            source="BAN",
            point=geom.point_on_surface,
            street_number="4",
            street_name="rue scipion",
            city_name="Paris",
        )
        building = Building.objects.create(
            rnb_id="BDG-CONSTR",
            shape=geom,
            point=geom.point_on_surface,
            ext_ids={"some_source": "1234"},
        )
        building.addresses.add(address)
        building.save()

        directory_name = create_rnb_csv_files()
        
        # Check if the directory exists
        self.assertTrue(os.path.exists(directory_name))

        # check there are 3 files in the directory
        files = os.listdir(directory_name)
        self.assertEqual(len(files), 3)

        # open the building file and check the content
        with open(f"{directory_name}/rnb_building.csv", "r") as f:
            content = f.read()
            self.assertIn("id,rnb_id,point,created_at,updated_at,shape,ext_ids", content)
            self.assertIn("BDG-CONSTR", content)
            self.assertIn("1234", content)
            self.assertIn("MULTIPOLYGON", content)
            self.assertIn("POINT", content)
        
        # open the building address file and check the content
        with open(f"{directory_name}/rnb_building_address.csv", "r") as f:
            content = f.read()
            self.assertIn("building_id,address_id", content)
            self.assertIn(str(building.id), content)
            self.assertIn(str(address.id), content)

        # open the address file and check the content
        with open(f"{directory_name}/rnb_address.csv", "r") as f:
            content = f.read()
            self.assertIn("id,source,street_number,street_rep,street_name,street_type,city_name,city_zipcode,created_at,updated_at,point,city_insee_code", content)
            self.assertIn("BAN", content)
            self.assertIn("4", content)
            self.assertIn("rue scipion", content)
            self.assertIn("Paris", content)

        (archive_path, archive_size, archive_sha1) = create_archive(directory_name)

        # check the archive exists
        self.assertTrue(os.path.exists(archive_path))
        self.assertEqual(archive_size, os.path.getsize(archive_path))
        # assert sha is not empty
        self.assertTrue(archive_sha1)

        cleanup_directory(directory_name)

        # check the directory has been removed
        self.assertFalse(os.path.exists(directory_name))