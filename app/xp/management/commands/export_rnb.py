# empty django command
import json

from django.core.management import BaseCommand
from django.db import connections

from batid.services.source import Source


class Command(BaseCommand):
    def handle(self, *args, **options):
        src = Source("xp-grenoble-export_rnb")

        q = (
            "SELECT b.rnb_id, b.source, ST_AsGeoJSON(b.shape) as shape "
            "FROM batid_building as b "
        )

        with connections["default"].cursor() as cursor:
            cursor.execute(q)
            r = cursor.fetchall()

            # export the result to a geojson featurecollection
            # with a property rnb_id
            # and a property source

            feature_collection = {"type": "FeatureCollection", "features": []}

            for rnb_id, source, shape in r:
                print(rnb_id, source)

                feature = {
                    "type": "Feature",
                    "properties": {"rnb_id": rnb_id, "source": source},
                    "geometry": json.loads(shape),
                }
                feature_collection["features"].append(feature)

            with open(src.path, "w") as f:
                json.dump(feature_collection, f)
