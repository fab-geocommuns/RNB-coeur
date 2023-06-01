from django.core.management.base import BaseCommand
import requests
from django.urls import get_resolver
from app.celery import app


class Command(BaseCommand):
    def handle(self, *args, **options):
        pass
