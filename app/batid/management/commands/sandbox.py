import uuid
from django.core.management.base import BaseCommand
from django.contrib.gis.geos import Point
from batid.services.imports.import_bal import find_bdg_to_link, create_dpt_bal_rnb_links


class Command(BaseCommand):
    def handle(self, *args, **kwargs):

        create_dpt_bal_rnb_links({"dpt": "33"}, uuid.uuid4())
