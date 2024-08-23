import inspect

from django.urls import get_resolver
from rest_framework.schemas.generators import BaseSchemaGenerator
from rest_framework.schemas.generators import EndpointEnumerator
from rest_framework.views import APIView
from rest_framework.viewsets import ViewSetMixin


def rnb_doc(path_desc):
    def decorator(fn):
        fn._in_rnb_doc = True
        fn._path_desc = path_desc
        return fn

    return decorator


def build_schema():
    # goes through all methods and checks if they have add_to_doc attribute
    # if they do, it adds them to the schema

    schema = {
        "openapi": "3.0.3",
        "info": {"title": "Test API", "version": "1.0.0"},
        "paths": _get_paths(),
    }

    return schema


def _get_endpoints() -> list:

    url_resolver = get_resolver()
    all_patterns = url_resolver.url_patterns

    inspector = EndpointEnumerator()
    return inspector.get_api_endpoints(all_patterns)


def _add_fn_doc(path, fn, schema_paths) -> dict:

    if hasattr(fn, "_in_rnb_doc"):
        if path not in schema_paths:
            schema_paths[path] = {}

        schema_paths[path].update(fn._path_desc)

    return schema_paths


def _get_paths() -> dict:

    schema_paths = {}

    generator = BaseSchemaGenerator()

    for path, method, callback in _get_endpoints():

        # We have to instantiate the view to get the action and its associated method
        view = generator.create_view(callback, method)

        if isinstance(view, ViewSetMixin):
            action = getattr(view, view.action)
        elif isinstance(view, APIView):
            action = getattr(view, method.lower())
        else:
            raise Exception("Unknown view type when generating schema")

        # We attach the function/method rnb_doc if it has any
        if inspect.ismethod(action):
            fn = action.__func__
            schema_paths = _add_fn_doc(path, fn, schema_paths)

        if inspect.isfunction(action):
            schema_paths = _add_fn_doc(path, action, schema_paths)

    return schema_paths
