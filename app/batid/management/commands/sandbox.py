import os

from django.core.management.base import BaseCommand

from batid.services.mattermost import _notifications_are_active
from batid.services.mattermost import notify_tech


class Command(BaseCommand):
    def handle(self, *args, **kwargs):

        print(os.environ.get("MATTERMOST_RNB_TECH_WEBHOOK_URL"))
        print(_notifications_are_active())

        notify_tech("Test notification")
