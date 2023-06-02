from django.core.management.base import BaseCommand
from batid.services.signal import create_signal
from batid.models import Building
from django.contrib.auth.models import User


class Command(BaseCommand):
    def handle(self, *args, **options):
        b = Building.objects.all().first()
        u = User.objects.get(username="paul")

        s = create_signal(
            type="test",
            building=b,
            origin="testOrigin",
            creator=u,
        )
