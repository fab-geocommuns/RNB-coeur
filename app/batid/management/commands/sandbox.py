import json
import os
from pprint import pprint

from django.contrib.gis.geos import GEOSGeometry
from django.core.management.base import BaseCommand
from django.db import connections
from django.conf import settings
from batid.models import Candidate
import pandas as pd
from batid.logic.source import Source
from app.celery import app as celery_app
from celery import chain, Signature


class Command(BaseCommand):



    def handle(self, *args, **options):

        # print(celery_app)

        print('send task')

        res = chain(
            Signature('tasks.add', args=[1, 2]), Signature('tasks.add', args=[8,4], immutable=True))()
        print(res.get())


        # task = celery_app.send_task('tasks.chain_task', args=[3, 6])
        # print(task.get())

        # celery_app.control.purge()




































