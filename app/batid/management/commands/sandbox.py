import os

from django.core.management.base import BaseCommand

from api_alpha.utils.rnb_doc import build_schema_dict
from batid.services.mattermost import notify_tech, _notifications_are_active


class Command(BaseCommand):
    def handle(self, *args, **kwargs):

        print(os.environ.get("MATTERMOST_RNB_TECH_WEBHOOK_URL"))
        print(_notifications_are_active())

        notify_tech("Test notification")
