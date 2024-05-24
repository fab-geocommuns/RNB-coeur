from django.core.management.base import BaseCommand

from batid.models import Building


class Command(BaseCommand):
    help = "Remove one building"

    def add_arguments(self, parser):
        parser.add_argument("bdg", type=str)

    def handle(self, *args, **options):
        b = Building.objects.filter(rnb_id=options["bdg"])

        if b.count() == 0:
            self.stdout.write("Building not found")
            return

        self.stdout.write(f"Building found: {b[0].rnb_id}")

        confirm = input(f"Type 'REMOVEBDG' to confirm: ")

        if confirm != f"REMOVEBDG":
            print("Aborting")
            return

        b[0].delete()
