import json

from django.contrib.gis.geos import GEOSGeometry
from django.core.management.base import BaseCommand
from batid.list_bdg import list_bdgs
from batid.services.building import add_default_status
from batid.services.candidate_new import Inspector
from batid.services.guess_bdg import BuildingGuess
from batid.services.imports.import_bdnb_2023_01 import import_bdnd_2023_01_bdgs
from batid.services.source import Source
from batid.tasks import dl_source

from batid.models import Candidate, Building, BuildingStatus
from batid.services.bdg_status import BuildingStatus as BuildingStatusService


class Command(BaseCommand):
    def handle(self, *args, **options):
        cent = GEOSGeometry(
            json.dumps(
                {
                    "coordinates": [
                        [
                            [5.721173186219147, 45.18449241134684],
                            [5.721173186219147, 45.18444585797988],
                            [5.721262369668409, 45.18444585797988],
                            [5.721262369668409, 45.18449241134684],
                            [5.721173186219147, 45.18449241134684],
                        ]
                    ],
                    "type": "Polygon",
                }
            )
        )
        cent.srid = 4326

        troisquarts = GEOSGeometry(
            json.dumps(
                {
                    "coordinates": [
                        [
                            [5.7211730732533965, 45.18449252775494],
                            [5.7211730732533965, 45.18444570055911],
                            [5.721240283689895, 45.18444570055911],
                            [5.721240283689895, 45.18449252775494],
                            [5.7211730732533965, 45.18449252775494],
                        ]
                    ],
                    "type": "Polygon",
                }
            )
        )
        troisquarts.srid = 4326

        double = GEOSGeometry(
            json.dumps(
                {
                    "coordinates": [
                        [
                            [5.721173073253794, 45.184492618505715],
                            [5.721173073253794, 45.18444579131017],
                            [5.721348438414395, 45.18444579131017],
                            [5.721348438414395, 45.184492618505715],
                            [5.721173073253794, 45.184492618505715],
                        ]
                    ],
                    "type": "Polygon",
                }
            )
        )
        double.srid = 4326

        guadeloupe_cent = GEOSGeometry(
            json.dumps(
                {
                    "coordinates": [
                        [
                            [-61.66076541822875, 16.17452634924382],
                            [-61.66076541822875, 16.174204129914514],
                            [-61.660207035430034, 16.174204129914514],
                            [-61.660207035430034, 16.17452634924382],
                            [-61.66076541822875, 16.17452634924382],
                        ]
                    ],
                    "type": "Polygon",
                }
            )
        )
        guadeloupe_cent.srid = 4326

        guadeloupe_troisquarts = GEOSGeometry(
            json.dumps(
                {
                    "coordinates": [
                        [
                            [-61.66076528606351, 16.174528079834246],
                            [-61.66076528606351, 16.17420482081107],
                            [-61.6603380865278, 16.17420482081107],
                            [-61.6603380865278, 16.174528079834246],
                            [-61.66076528606351, 16.174528079834246],
                        ]
                    ],
                    "type": "Polygon",
                }
            )
        )

        # Convert to Lambert to check ratio in meters
        cent_lamb = cent.transform(2154, clone=True)
        troisquarts_lamb = troisquarts.transform(2154, clone=True)
        double_lamb = double.transform(2154, clone=True)
        guadeloupe_cent_lamb = guadeloupe_cent.transform(2154, clone=True)
        guadeloupe_troisquarts_lamb = guadeloupe_troisquarts.transform(2154, clone=True)

        print("lambert areas")
        print("cent area ", cent_lamb.area)
        print("trois quart area ", troisquarts_lamb.area)
        print("double area ", double_lamb.area)
        print("guadeloupe cent area ", guadeloupe_cent.area)
        print("guadeloupe trois quart area ", guadeloupe_troisquarts.area)

        print("wgs84 areas")
        print("cent area ", cent.area)
        print("trois quart area ", troisquarts.area)
        print("double area ", double.area)
        print("guadeloupe cent area ", guadeloupe_cent.area)
        print("guadeloupe trois quart area ", guadeloupe_troisquarts.area)

        print("trois quart area ratio Lambert ", troisquarts_lamb.area / cent_lamb.area)
        print("trois quart area ratio ", troisquarts.area / cent.area)

        print("double area ratio Lambert ", double_lamb.area / cent_lamb.area)
        print("double area ratio ", double.area / cent.area)

        print(
            "guadeloupe trois quart area ratio Lambert ",
            guadeloupe_troisquarts_lamb.area / guadeloupe_cent_lamb.area,
        )
        print(
            "guadeloupe trois quart area ratio ",
            guadeloupe_troisquarts.area / guadeloupe_cent.area,
        )
