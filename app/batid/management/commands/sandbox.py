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
        print(schema)

        # url_resolver = get_resolver()
        # all_patterns = url_resolver.url_patterns
        #
        # inspector = EndpointEnumerator()
        # endpoints = inspector.get_api_endpoints(all_patterns)
        #
        # for endpoint in endpoints:
        #     path, method, callback = endpoint
        #     print("---")
        #     print(path, method, callback)
        #
        #     generator = BaseSchemaGenerator()
        #     view = generator.create_view(callback, method)
        #
        #     if isinstance(view, ViewSetMixin):
        #         action = getattr(view, view.action)
        #     elif isinstance(view, APIView):
        #         action = getattr(view, method.lower())
        #     else:
        #         raise Exception("Unknown view type")
        #
        #     if inspect.ismethod(action):
        #
        #         fn = action.__func__
        #
        #         if hasattr(fn, "_in_rnb_doc"):
        #             print("in rnb doc")
