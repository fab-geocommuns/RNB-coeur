import inspect

from django.core.management.base import BaseCommand
from django.urls import get_resolver
from rest_framework.schemas import SchemaGenerator
from rest_framework.schemas.generators import EndpointEnumerator, BaseSchemaGenerator
from rest_framework.views import APIView
from rest_framework.viewsets import ViewSetMixin

from api_alpha.utils.rnb_doc import build_schema

from api_alpha.urls import urlpatterns, router


class Command(BaseCommand):
    def handle(self, *args, **kwargs):

        schema = build_schema()

        # then, we should convert to YML
        # it might be useful to check it against an OpenAPI schema validator (or it can be done in test)

        print(schema)
