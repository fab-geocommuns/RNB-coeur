import json

from django.core.management.base import BaseCommand
from django.db import connection

from app.celery import app
from batid.services.source import Source
from batid.tests.helpers import in_village


class Command(BaseCommand):
    @in_village
    def handle(self, *args, **options):
        cursor = connection.cursor()
        q = """SELECT json_build_object(
            'type', 'FeatureCollection',
            'features', json_agg(ST_AsGeoJSON(limited_building.*)::json)
        ) 
        FROM (
            SELECT ST_Transform(b.shape, 4326), b.*, array_agg(json_build_object('address_id', ba.id, 'address', CONCAT(ba.street_number, ' ', ba.street_rep, ' ', ba.street_type, ' ',  ba.street_name, ', ',  ba.city_name))) as add_id FROM batid_building as b
            join batid_building_addresses bba on bba.building_id = b.id
            join batid_address ba on bba.address_id = ba.id
            group by b.id 
        ) as limited_building;"""

        cursor.execute(q)
        data = cursor.fetchone()

        source = Source(
            "village_geojson",
            custom_ref={"folder": "village", "filename": "village.geojson"},
        )

        json_obj = json.dumps(data, indent=4)

        with open(source.path, "w") as f:
            f.write(json_obj)
