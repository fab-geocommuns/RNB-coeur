from django.core.management.base import BaseCommand

from api_alpha.utils.rnb_doc import build_schema


class Command(BaseCommand):
    def handle(self, *args, **kwargs):

        schema = build_schema()

        # then, we should convert to YML
        # it might be useful to check it against an OpenAPI schema validator (or it can be done in test)

        print(schema)
