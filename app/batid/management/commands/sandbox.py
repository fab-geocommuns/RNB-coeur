import json
from pprint import pprint

import geopandas as gpd
from django.contrib.gis.geos import GEOSGeometry
from django.core.management.base import BaseCommand
from django.core.serializers import serialize
from shapely.geometry import mapping

from batid.models import Building
from batid.services.guess_bdg_new import Guesser, PartialRoofHandler


class Command(BaseCommand):
    def handle(self, *args, **options):
        gdf = gpd.read_file(
            "notebooks/rapprochements/lyon/export_rnb.gpkg", layer="toit"
        )
        srid = gdf.crs.to_epsg()

        target_id = str(138328)

        inputs = []
        for idx, row in gdf.iterrows():
            if str(row["id"]) == target_id:
                inputs.append(to_input(row, srid))

        guesser = Guesser()
        guesser.handlers = [PartialRoofHandler()]
        guesser.load_inputs(inputs)
        guesser.guess_all()
        pprint(guesser.guesses)
        print(guesser.guesses[target_id]["match"].rnb_id)


def to_input(row, srid):
    geom_geojson = mapping(row["geometry"])
    geom = GEOSGeometry(json.dumps(geom_geojson))
    geom.srid = srid
    geom.transform(4326)

    return {"ext_id": row["id"], "polygon": json.loads(geom.json)}
