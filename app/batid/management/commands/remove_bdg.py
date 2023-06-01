from batid.models import Building
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Remove one building"

    def add_arguments(self, parser):
        parser.add_argument("bdg", type=str)

    def handle(self, *args, **options):
        b = Building.objects.filter(rnb_id=options["bdg"])

        if b.count() == 0:
            self.stdout.write("Building not found")
            return

        confirm = input(f"Type 'REMOVEBDG' to confirm: ")

        if confirm != f"REMOVEBDG":
            print("Aborting")
            return
