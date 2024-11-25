from django.core.management.base import BaseCommand

from batid.services.administrative_areas import validate_dpt_code
from batid.services.imports.import_dpt import import_one_department


class Command(BaseCommand):
    help = "Import shape and name of a department"

    def add_arguments(self, parser):
        parser.add_argument("dpt", type=str)

    def handle(self, *args, **options):

        print(f"Importing department {options['dpt']}")

        if validate_dpt_code(options["dpt"]):
            import_one_department(options["dpt"])

        print("Done")
