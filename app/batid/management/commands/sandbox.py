from django.core.management.base import BaseCommand

from api_alpha.utils.rnb_doc import build_schema


class Command(BaseCommand):
    def handle(self, *args, **options):

        schema = build_schema(["api_alpha.views"])

        # then, transform dict into yml

        print(schema)
