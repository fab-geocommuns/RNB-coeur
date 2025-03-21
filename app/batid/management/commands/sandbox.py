from django.core.management.base import BaseCommand
from django.core.mail import send_mail, get_connection


class Command(BaseCommand):
    def handle(self, *args, **kwargs):

        connection = get_connection()

        print("host ", connection.host)
        print("port ", connection.port)
        print("username ", connection.username)
        print("password ", connection.password)
        print("use_tls ", connection.use_tls)
        print("use_ssl ", connection.use_ssl)

        send_mail(
            "Test du sujet",
            "test du message",
            "ne-pas-repondre@rnb.beta.gouv.fr",
            ["paul.etienney@beta.gouv.fr", "paul@donatello.dev"],
            fail_silently=False,
        )
