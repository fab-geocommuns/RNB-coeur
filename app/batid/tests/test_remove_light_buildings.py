import geopandas as gpd
from django.contrib.auth.models import User
from django.test import TransactionTestCase

from batid.models import Building
from batid.models import Fix
from batid.services.rnb_corrections.remove_light_buildings import remove_buildings

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
        fix = Fix.objects.create(
            user=user,
            text="Oh oh, nous avons importé des bâtiments légers alors que nous n'aurions pas dû",
        )

        remove_buildings(bd_topo_path, user.username, fix.id, max_workers=1)

        # if you need to really understand the test case, open the fixtures files in QGIS

        # 1 is referenced in the bdtopo by A but does not intersect it
        # 3 is referenced in the bdtopo by C but is not included in C (it is bigger)
        # 6 is referenced in the bdtopo by E and is included in E, but E is not a light building
        active_rnb_ids = [
            b.rnb_id for b in Building.objects.filter(is_active=True).all()
        ]
        active_rnb_ids.sort()
        self.assertEqual(active_rnb_ids, ["1", "3", "6"])

        # 2 is referenced in the bdtopo by B and is included in B, and B is a light building
        # case of two rnb_ids linked to one bdtopo building:
        #    4 is referenced in the bdtopo by D and is included in D, and D is a light building
        #    5 is referenced in the bdtopo by D and is included in D, and D is a light building
        inactive_rnb_ids = [
            b.rnb_id for b in Building.objects.filter(is_active=False).all()
        ]
        inactive_rnb_ids.sort()
        self.assertEqual(inactive_rnb_ids, ["2", "4", "5"])

        # check that a deleted building has all the information expected
        b = Building.objects.get(rnb_id="2")
        self.assertEqual(b.is_active, False)
        self.assertEqual(b.event_type, "delete")
        self.assertEqual(b.event_origin, {"source": "fix", "id": fix.id})
        self.assertEqual(b.event_user, user)
