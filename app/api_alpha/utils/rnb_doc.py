import inspect

from django.conf import settings
from django.urls import get_resolver
from django.urls import reverse
from rest_framework.schemas.generators import BaseSchemaGenerator
from rest_framework.schemas.generators import EndpointEnumerator
from rest_framework.views import APIView
from rest_framework.viewsets import ViewSetMixin

from batid.services.bdg_status import BuildingStatus

COMMON_RESPONSES = {
    "400": {"description": "Requête invalide (données mal formatées ou incomplètes)."},
    "429": {
        "description": "Le quota de requêtes a été atteint. Un quota maximal de 20 requêtes par secondes est appliqué, mais celui-ci peut varier par requête.\nVeuillez consulter les headers HTTP de la réponse pour plus d'informations concernant le quota."
    },
}


def rnb_doc(path_desc, schemes=[]):
    for _, desc in path_desc.items():
        method_responses = desc.get("responses", {})
        for code, response in COMMON_RESPONSES.items():
            if code not in method_responses:
                method_responses[code] = response
        desc["responses"] = method_responses

    def decorator(fn):
        fn._in_rnb_doc = True
        fn._path_desc = path_desc

        schemes.append("all")
        fn._schemes = schemes

        return fn

    return decorator


def build_schema_all_endpoints() -> dict:
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
        "paths": _get_paths("all"),
        "components": _get_components(),
    }

    return schema


def build_schema_ogc_endpoints(request) -> dict:

    # OGC standard seems to require that the server url is the path to the API root
    # and all paths are relative to that root
    # In order to do so, we have to make a bit of a hack here

    ogc_root = reverse("ogc_root")

    # For each path, we remove the ogc_root prefix
    paths = _get_paths("ogc")
    ogc_rooted_paths = {}
    for path, path_desc in paths.items():

        new_key = path.replace(ogc_root, "/")
        ogc_rooted_paths[new_key] = path_desc

    schema = {
        # Specs of the 3.1.0 version of the OpenAPI: https://spec.openapis.org/oas/latest.html
        "openapi": "3.1.0",
        "info": {
            "title": "RNB OGC API",
            "version": "ogc",
            "description": "API Référentiel National des Bâtiments au standard OGC",
        },
        "servers": [
            {
                "url": request.build_absolute_uri(ogc_root).rstrip("/"),
            }
        ],
        "paths": ogc_rooted_paths,
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


def get_status_list():
    return [status["key"] for status in BuildingStatus.TYPES]


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
                    "street": {
                        "type": "string",
                        "description": "Nom de la voie",
                        "example": "rue de l'église",
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
            "BuildingWPlots": {
                "type": "object",
                "properties": {
                    "plots": {
                        "type": "array",
                        "description": "Liste des parcelles cadastrales intersectant le bâtiment. Disponible si le paramètre <pre>withPlots=1</pre> est intégré à l'URL de requête. NB: il s'agit d'un croisement géométrique et non d'une donnée fiscale. Il arrive parfois qu'un bâtiment intersecte une mauvaise parcelle du fait d'un décalage géographique entre les bâtiments du cadastre et ceux du RNB. Nous fournissons avec chaque parcelle cadastrale le taux d'intersection du bâtiment avec celle-ci. Les parcelles intersectant largement un bâtiment sont plus susceptibles d'être réellement associées à ce bâtiment d'un point de vue fiscal.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {
                                    "type": "string",
                                    "description": "Identifiant de la parcelle.",
                                    "example": "01402000AB0051",
                                },
                                "bdg_cover_ratio": {
                                    "type": "number",
                                    "description": "Taux d'intersection du bâtiment par la parcelle. Ce taux est compris entre 0 et 1. Un taux de 1 signifie que la parcelle couvre entièrement le bâtiment.",
                                    "example": 0.403,
                                },
                            },
                        },
                    }
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
                        "description": "Géométrie du bâtiment au format GeoJSON. Le système de référence géodésique est le WGS84. Elle peut être un multipolygone, un polygone ou un point et correspond notre meilleure connaissance de la réalité:",
                        "properties": {
                            "type": {
                                "type": "string",
                                "enum": ["Point", "Polygon", "MultiPolygon"],
                                "example": "Point",
                            },
                            "coordinates": {
                                "type": "array",
                                "items": {
                                    "oneOf": [
                                        {
                                            "type": "array",
                                            "description": "Coordonnées pour un Point",
                                            "items": {"type": "number"},
                                            "example": [
                                                -0.570505392116188,
                                                44.841034137099996,
                                            ],
                                        },
                                        {
                                            "type": "array",
                                            "description": "Coordonnées pour un Polygon",
                                            "items": {
                                                "type": "array",
                                                "items": {"type": "number"},
                                            },
                                            "example": [
                                                [
                                                    [
                                                        -0.570505392116188,
                                                        44.841034137099996,
                                                    ],
                                                    [
                                                        -0.570505392116188,
                                                        44.841034137099996,
                                                    ],
                                                ]
                                            ],
                                        },
                                        {
                                            "type": "array",
                                            "description": "Coordonnées pour un MultiPolygon",
                                            "items": {
                                                "type": "array",
                                                "items": {
                                                    "type": "array",
                                                    "items": {"type": "number"},
                                                },
                                            },
                                            "example": [
                                                [
                                                    [
                                                        [
                                                            -0.570505392116188,
                                                            44.841034137099996,
                                                        ],
                                                        [
                                                            -0.570505392116188,
                                                            44.841034137099996,
                                                        ],
                                                    ]
                                                ]
                                            ],
                                        },
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


def _get_endpoints() -> list:

    url_resolver = get_resolver()
    all_patterns = url_resolver.url_patterns

    inspector = EndpointEnumerator()
    return inspector.get_api_endpoints(all_patterns)


def _add_fn_doc(schema_to_build, path, fn, schema_paths) -> dict:

    if hasattr(fn, "_in_rnb_doc"):

        if schema_to_build in fn._schemes:

            if path not in schema_paths:
                schema_paths[path] = {}

            schema_paths[path].update(fn._path_desc)

    return schema_paths


def _get_paths(schema_to_build: str) -> dict:

    schema_paths = {}  # type: ignore[var-annotated]

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
            schema_paths = _add_fn_doc(schema_to_build, path, fn, schema_paths)

        if inspect.isfunction(action):
            schema_paths = _add_fn_doc(schema_to_build, path, action, schema_paths)

    return schema_paths
