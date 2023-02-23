import os
from pprint import pprint

from django.core.management.base import BaseCommand
import subprocess

class Command(BaseCommand):


    def handle(self, *args, **options):

        subprocess.Popen(["pg_restore"])







