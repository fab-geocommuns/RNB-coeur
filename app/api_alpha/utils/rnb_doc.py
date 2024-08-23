import importlib
import inspect
import sys


def rnb_doc(path_key, path_desc):

    def decorator(fn):
        fn._in_rnb_doc = True
        fn._path_key = path_key
        fn._path_desc = path_desc
        return fn

    return decorator


def build_schema(modules_names):
    # goes through all methods and checks if they have add_to_doc attribute
    # if they do, it adds them to the schema

    schema = {
        "openapi": "3.0.3",
        "info": {"title": "Test API", "version": "1.0.0"},
        "paths": _get_paths(modules_names),
    }

    for name, obj in inspect.getmembers(sys.modules[__name__]):
        if hasattr(obj, "add_to_doc"):
            schema["paths"].update(obj())

    return schema


def _get_paths(modules_names):

    paths = {}

    for module_name in modules_names:

        module = importlib.import_module(module_name)

        for name, obj in inspect.getmembers(module):

            if (
                inspect.isfunction(obj)
                and hasattr(obj, "_in_rnb_doc")
                and obj._in_rnb_doc
            ):
                if obj._path_key not in paths:
                    paths[obj._path_key] = {}

                paths[obj._path_key].update(obj._path_desc)

            elif inspect.isclass(obj):
                for method_name, method in inspect.getmembers(obj):
                    if (
                        inspect.isfunction(method)
                        and hasattr(method, "_in_rnb_doc")
                        and method._in_rnb_doc
                    ):
                        if method._path_key not in paths:
                            paths[method._path_key] = {}

                        paths[method._path_key].update(method._path_desc)

    return paths
