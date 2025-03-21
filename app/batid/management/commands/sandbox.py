from django.core.management.base import BaseCommand

from batid.services.imports.import_ban import import_ban_addresses


class Command(BaseCommand):
    def handle(self, *args, **kwargs):

        # src = Source("ban")
        # src.set_params({"dpt": "75"})

        # src.download()
        # src.uncompress()

        import_ban_addresses({"dpt": "75"})
