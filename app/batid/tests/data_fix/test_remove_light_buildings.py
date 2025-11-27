import os
import shutil

import geopandas as gpd
from django.conf import settings
from django.contrib.auth.models import User
from django.test import TransactionTestCase

from batid.models import Building
from batid.models import DataFix
from batid.models import UserProfile
from batid.services.data_fix.remove_light_buildings import buildings_to_remove
from batid.services.data_fix.remove_light_buildings import remove_light_buildings
from batid.services.data_fix.remove_light_buildings import save_results_as_file


# we use TransactionTestCase beacause of the ThreadPoolExecutor use
class TestRemoveLightBuildings(TransactionTestCase):
    def test_remove_light_buildings(self):
        rnb_df = gpd.read_file(
            "batid/fixtures/remove_light_buildings/sample_rnb.geojson"
        )

        # create RNB Buildings from the geojson
        for i, row in rnb_df.iterrows():
            Building.objects.create(
                rnb_id=row["rnb_id"],
                shape=row["geometry"].wkt,
                is_active=True,
            )

        buildings = Building.objects.all()

        # a sample of the bdtopo, containing 5 buildings linked to the RNB ones
        # inserted just above
        bd_topo_path = "batid/fixtures/remove_light_buildings/sample_bdtopo.shp"

        user = User.objects.create_user(username="jean")
        UserProfile.objects.create(user=user)
        datafix = DataFix.objects.create(
            user=user,
            text="Oh oh, nous avons importé des bâtiments légers alors que nous n'aurions pas dû",
        )

        buildings = buildings_to_remove(bd_topo_path, max_workers=1)

        self.assertEqual(len(buildings), 3)

        # create a folder to save the results
        folder_name = os.path.join(
            settings.WRITABLE_DATA_DIR, "test_remove_light_buildings"
        )

        if os.path.exists(folder_name):
            shutil.rmtree(folder_name)
        os.makedirs(folder_name)

        save_results_as_file(buildings, "33", folder_name)
        remove_light_buildings(folder_name, user.username, datafix.id)

        # folder should be deleted if transaction succeeded
        self.assertFalse(os.path.exists(folder_name))

        # database should be updated
        # if you need to really understand the test case, open the fixtures files in QGIS

        # 1 is referenced in the bdtopo by A but does not intersect it
        # 11 is referenced in the bdtopo by A and intersects it but has no neighbors
        # 3 is referenced in the bdtopo by C but is not included in C (it is bigger)
        # 6 is referenced in the bdtopo by E and is included in E, but E is not a light building
        # 20, 21, 22 are not referenced in the bdtopo and are just here to be neighbors
        # 30 is referenced in the bdtopo by D, is including in D, has a neighbor, but is too big
        active_rnb_ids = [
            b.rnb_id for b in Building.objects.filter(is_active=True).all()
        ]
        active_rnb_ids.sort()
        self.assertEqual(active_rnb_ids, ["1", "11", "20", "21", "22", "3", "30", "6"])

        # 2 is referenced in the bdtopo by B and is included in B, and B is a light building
        # case of two rnb_ids linked to one bdtopo building:
        #    4 is referenced in the bdtopo by D and is included in D, and D is a light building
        #    5 is referenced in the bdtopo by D and is included in D, and D is a light building
        inactive_rnb_ids = [
            b.rnb_id for b in Building.objects.filter(is_active=False).all()
        ]
        inactive_rnb_ids.sort()
        self.assertEqual(inactive_rnb_ids, ["2", "4", "5"])

        # check that a deactivated building has all the information expected
        b = Building.objects.get(rnb_id="2")
        self.assertEqual(b.is_active, False)
        self.assertEqual(b.event_type, "deactivation")
        self.assertEqual(b.event_origin, {"source": "data_fix", "id": datafix.id})
        self.assertEqual(b.event_user, user)
