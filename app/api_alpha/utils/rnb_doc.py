import inspect

import yaml
from django.conf import settings
from django.urls import get_resolver
from rest_framework.schemas.generators import BaseSchemaGenerator
from rest_framework.schemas.generators import EndpointEnumerator
from rest_framework.views import APIView
from rest_framework.viewsets import ViewSetMixin

from batid.services.bdg_status import BuildingStatus


def rnb_doc(path_desc):
    def decorator(fn):
        fn._in_rnb_doc = True
        fn._path_desc = path_desc
        return fn

    return decorator


def build_schema_dict():
    # goes through all methods and checks if they have add_to_doc attribute
    # if they do, it adds them to the schema

    schema = {
        # Specs of the 3.1.0 version of the OpenAPI: https://spec.openapis.org/oas/latest.html
        "openapi": "3.1.0",
        "info": {
            "title": "API du Référentiel National des Bâtiments",
            "version": "alpha",
        },
        "servers": [
            {
                "url": settings.URL,
                "description": "API du Référentiel National des Bâtiments",
            }
        ],
        "paths": _get_paths(),
        "components": _get_components(),
    }

    return schema


def get_status_html_list():
    all_stats = [(status["key"], status["label"]) for status in BuildingStatus.TYPES]
    html_list = "<ul>"
    for status in all_stats:
        html_list += f"<li><b>{status[0]}</b> : {status[1]}</li>"
    html_list += "</ul>"

    return html_list


def _get_components() -> dict:
    return {
        "schemas": {
            "BuildingAddress": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Identifiant de l'adresse au sein de la Base Adresse Nationale (BAN)",
                        "example": "02191_0020_00003",
                    },
                    "source": {
                        "type": "string",
                        "description": "Source du lien bâtiment ↔ adresse",
                        "example": "bdnb",
                    },
                    "street_number": {
                        "type": "string",
                        "description": "Numéro de la voie",
                        "example": "3",
                        "nullable": True,
                    },
                    "street_rep": {
                        "type": "string",
                        "description": "Indice de répétition du numéro de la voie",
                        "example": "bis",
                        "nullable": True,
                    },
                    "street_type": {
                        "type": "string",
                        "description": "Type de la voie",
                        "example": "rue",
                        "nullable": True,
                    },
                    "street_name": {
                        "type": "string",
                        "description": "Nom de la voie",
                        "example": "de l'église",
                        "nullable": True,
                    },
                    "city_name": {
                        "type": "string",
                        "description": "Nom de la commune",
                        "example": "Chivy-lès-Étouvelles",
                    },
                    "city_zipcode": {
                        "type": "string",
                        "description": "Code postal de la commune",
                        "example": "02000",
                    },
                    "city_insee_code": {
                        "type": "string",
                        "description": "Code INSEE de la commune",
                        "example": "02191",
                    },
                },
            },
            "Building": {
                "type": "object",
                "properties": {
                    "rnb_id": {
                        "type": "string",
                        "description": "Identifiant unique du bâtiment dans le RNB",
                        "example": "PG46YY6YWCX8",
                    },
                    "status": {
                        "type": "string",
                        "description": "Statut du bâtiment",
                        "enum": BuildingStatus.ALL_TYPES_KEYS,
                        "example": BuildingStatus.DEFAULT_STATUS,
                    },
                    "point": {
                        "type": "object",
                        "description": "Coordonnées géographiques du bâtiment au format GeoJSON. Le système de référence géodésique est le WGS84.",
                        "properties": {
                            "type": {"type": "string", "example": "Point"},
                            "coordinates": {
                                "type": "array",
                                "items": {"type": "number"},
                                "example": [-0.570505392116188, 44.841034137099996],
                            },
                        },
                    },
                    "shape": {
                        "type": "object",
                        "description": "Géométrie du bâtiment au format GeoJSON. Le système de référence géodésique est le WGS84. Elle peut être un multipolygone, un polygone, un point ou null",
                        "properties": {
                            "type": {
                                "type": "string",
                                "enum": ["Point", "Polygon", "MultiPolygon"],
                                "example": "Point"
                            },
                            "coordinates": {
                                "type": "array",
                                "items": {
                                    "oneOf": [
                                        {
                                            "type": "array",
                                            "description": "Coordonnées pour un Point",
                                            "items": {
                                                "type": "number"
                                            },
                                            "example": [-0.570505392116188, 44.841034137099996]
                                        },
                                        {
                                            "type": "array",
                                            "description": "Coordonnées pour un Polygon",
                                            "items": {
                                                "type": "array",
                                                "items": {
                                                    "type": "number"
                                                }
                                            },
                                            "example": [
                                                [
                                                    [-0.570505392116188, 44.841034137099996],
                                                    [-0.570505392116188, 44.841034137099996]
                                                ]
                                            ]
                                        },
                                        {
                                            "type": "array",
                                            "description": "Coordonnées pour un MultiPolygon",
                                            "items": {
                                                "type": "array",
                                                "items": {
                                                    "type": "array",
                                                    "items": {
                                                        "type": "number"
                                                    }
                                                }
                                            },
                                            "example": [
                                                [
                                                    [
                                                        [-0.570505392116188, 44.841034137099996],
                                                        [-0.570505392116188, 44.841034137099996]
                                                    ]
                                                ]
                                            ]
                                        }
                                    ]
                                },
                            },
                        },
                    },
                    "addresses": {
                        "type": "array",
                        "description": "Liste des adresses du bâtiment",
                        "items": {"$ref": "#/components/schemas/BuildingAddress"},
                    },
                    "ext_ids": {
                        "type": "array",
                        "description": "Le ou les identifiants de ce bâtiments au sein de la BD Topo et de la BDNB",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {
                                    "type": "string",
                                    "description": "Identifiant de ce bâtiment au sein de la BD Topo ou de la BDNB",
                                    "example": "bdnb-bc-3B85-TYM9-FDSX",
                                },
                                "source": {
                                    "type": "string",
                                    "description": "Base de donnée contenant de l'identifiant",
                                    "example": "bdnb",
                                },
                                "source_version": {
                                    "type": "string",
                                    "description": "Version de la base de donnée contenant l'identifiant",
                                    "example": "2023_01",
                                    "nullable": True,
                                },
                                "created_at": {
                                    "type": "string",
                                    "description": "Date de création du lien entre l'identifiant RNB et l'identfiant externe",
                                    "example": "2023-12-07T13:20:58.310444+00:00",
                                },
                            },
                        },
                    },
                },
            },
        },
    }


def build_schema_yml():
    schema_dict = build_schema_dict()

    return yaml.dump(schema_dict, default_flow_style=False, allow_unicode=True)


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
