from django.core.management.base import BaseCommand


class Command(BaseCommand):
    data_path = (
        "notebooks/rapprochements/enseignement_superieur/data/bat_rnb_mesr_complet.csv"
    )

    work_file = "notebooks/rapprochements/enseignement_superieur/results/guess.json"

    def handle(self, *args, **options):
        h = "hello"
