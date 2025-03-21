from django.core.management.base import BaseCommand
from django.core.mail import send_mail, get_connection


class Command(BaseCommand):
    def handle(self, *args, **kwargs):

        pass
