# empty django command
from app.celery import app as celery_app
from celery import chain, Signature


from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help = 'Import data for a departement'

    def add_arguments(self, parser):
        parser.add_argument('dpt', type=str)

    def handle(self, *args, **options):

        dpt = options['dpt']

        # BD Topo departements are zero-prefixed 3 digits codes.
        bdtopo_dpt = dpt.zfill(3)

        chain(
#            Signature('tasks.dl_source', args=["bdtopo", bdtopo_dpt]),
#            Signature('tasks.dl_source', args=["bdnb_7", dpt], immutable=True),
#            Signature('tasks.import_bdnb7', args=[dpt], immutable=True),
            Signature('tasks.import_bdtopo', args=[bdtopo_dpt], immutable=True),
            Signature('tasks.inspect_candidates', immutable=True)
        )()




