from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand

from batid.services.imports.import_bal import find_bdg_to_link


class Command(BaseCommand):
    def handle(self, *args, **kwargs):

        point = Point(-0.4531766790259805, 44.77780014817236, srid=4326)
        bdg = find_bdg_to_link(point, "33118_0060_00052_bis")
