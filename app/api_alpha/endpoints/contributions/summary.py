from api_alpha.exceptions import BadRequest
from api_alpha.utils.logging_mixin import RNBLoggingMixin
from api_alpha.utils.rnb_doc import rnb_doc
from batid.services.contribution_summary import (
    ALL_PERIOD,
    DEFAULT_WINDOW_DAYS,
    NEWCOMERS_LIMIT,
    RANKED_CITIES_LIMIT,
    TOP_LIMIT,
    WINDOWS_DAYS,
    get_all_contribution_rankings,
    get_all_contribution_summaries,
    get_contribution_summary,
)
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

# Response schemas, shared by the three endpoints

_PERIOD_PROPERTIES = {
    "updated_at": {
        "type": "string",
        "format": "date-time",
        "description": "Moment du calcul, le même pour toutes les périodes d'une réponse.",
        "example": "2026-11-20T10:00:00+01:00",
    },
    "window_days": {
        "type": ["integer", "null"],
        "description": "Nombre de jours de la période, null pour toute la période (days=all).",
        "example": 30,
    },
    "since": {
        "type": ["string", "null"],
        "format": "date-time",
        "description": "Début de la période, null pour toute la période (days=all), qui n'a pas de début.",
        "example": "2026-10-21T10:00:00+02:00",
    },
}

_COUNTS = {
    "type": "object",
    "properties": {
        "total": {
            "type": "integer",
            "description": "Nombre ayant contribué sur la période.",
        },
        "new": {
            "type": "integer",
            "description": "Nombre dont la toute première contribution tombe dans la période.",
        },
    },
    "required": ["total", "new"],
}

_USERNAME = {
    "type": "string",
    "description": "Nom d'utilisateur ; pour une adresse e-mail, seule la partie avant @ est publiée.",
}

_RANKED_USER = {
    "type": "object",
    "properties": {
        "username": _USERNAME,
        "organization": {
            "type": ["string", "null"],
            "description": "Nom court, sinon nom complet, de l'organisation actuelle du contributeur ; null s'il n'en a pas.",
        },
        "count": {
            "type": "integer",
            "description": "Nombre de contributions sur la période.",
        },
    },
    "required": ["username", "organization", "count"],
}

_RANKED_ORGANIZATION = {
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "description": "Nom court, sinon nom complet, de l'organisation.",
        },
        "count": {
            "type": "integer",
            "description": "Nombre de contributions de ses membres actuels sur la période.",
        },
    },
    "required": ["name", "count"],
}

_RANKED_CITY = {
    "type": "object",
    "properties": {
        "insee_code": {"type": "string", "example": "33522"},
        "name": {"type": "string", "example": "Talence"},
        "department": {
            "type": ["object", "null"],
            "description": "Département de la commune, null s'il n'est pas connu (collectivités d'outre-mer du Pacifique).",
            "properties": {
                "code": {"type": "string", "example": "33"},
                "name": {"type": "string", "example": "Gironde"},
            },
            "required": ["code", "name"],
        },
        "count": {
            "type": "integer",
            "description": "Nombre de contributions sur la commune sur la période.",
        },
    },
    "required": ["insee_code", "name", "department", "count"],
}

_USERS_DESCRIPTION = (
    "Contributeurs, les plus actifs d'abord. Les comptes désactivés ne sont pas "
    "listés ; leurs contributions restent comptées dans les totaux et pour leur "
    "organisation."
)


def _ranked_lists_properties(users_description: str) -> dict:
    return {
        "users": {
            "type": "array",
            "description": users_description,
            "items": _RANKED_USER,
        },
        "organizations": {
            "type": "array",
            "description": "Organisations, les plus actives d'abord.",
            "items": _RANKED_ORGANIZATION,
        },
        "cities": {
            "type": "array",
            "description": "Communes, les plus éditées d'abord.",
            "items": _RANKED_CITY,
        },
    }


SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        **_PERIOD_PROPERTIES,
        "cities": {
            **_COUNTS,
            "description": "Communes éditées sur la période (éditions faites depuis le 7 juillet 2025).",
        },
        "organizations": {
            **_COUNTS,
            "description": "Organisations ayant contribué sur la période, selon l'organisation actuelle de leurs membres.",
        },
        "contributions": {
            "type": "object",
            "properties": {
                "total": {
                    "type": "integer",
                    "description": "Nombre de contributions (demandes d'édition) de la période, imports exclus.",
                }
            },
            "required": ["total"],
        },
        "top": {
            "type": "object",
            "description": f"Les {TOP_LIMIT} plus actifs de la période.",
            "properties": _ranked_lists_properties(_USERS_DESCRIPTION),
            "required": ["users", "organizations", "cities"],
        },
        "newcomers": {
            "type": "object",
            "properties": {
                "users": {
                    "type": "array",
                    "description": (
                        f"Jusqu'à {NEWCOMERS_LIMIT} contributeurs dont la toute "
                        "première contribution tombe dans la période, les "
                        "derniers arrivés d'abord. Les comptes désactivés ne "
                        "sont pas listés."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {"username": _USERNAME},
                        "required": ["username"],
                    },
                }
            },
            "required": ["users"],
        },
    },
    "required": [
        *_PERIOD_PROPERTIES,
        "cities",
        "organizations",
        "contributions",
        "top",
        "newcomers",
    ],
}

RANKINGS_SCHEMA = {
    "type": "object",
    "properties": {
        **_PERIOD_PROPERTIES,
        **_ranked_lists_properties(_USERS_DESCRIPTION),
    },
    "required": [*_PERIOD_PROPERTIES, "users", "organizations", "cities"],
}


class ContributionSummaryView(RNBLoggingMixin, APIView):
    """
    GET /api/alpha/contributions/summary/
    Synthèse publique des contributions de la communauté, affichée sur la page
    d'accueil du site.
    """

    @rnb_doc(
        {
            "get": {
                "summary": "Synthèse des contributions de la communauté",
                "description": (
                    "Retourne en une seule réponse, pour une période (paramètre "
                    "days : les N derniers jours glissants, ou toutes les "
                    "contributions depuis toujours) : le nombre de "
                    "communes et d'organisations ayant contribué sur la période "
                    "(et celles dont c'est la toute première contribution), le "
                    "nombre de contributions de la période (contributions.total, "
                    f"imports exclus), les {TOP_LIMIT} "
                    "contributeurs, organisations et communes les plus actifs, et "
                    f"jusqu'à {NEWCOMERS_LIMIT} contributeurs ayant fait leur "
                    "toute première contribution sur la période, les derniers "
                    "arrivés d'abord. Les imports ne sont pas comptés comme des "
                    "contributions. Une contribution est une demande d'édition : "
                    "une fusion ou une scission compte une fois, quel que soit "
                    "le nombre de bâtiments concernés. Jusqu'en 2025, les "
                    "signalements corrigés comptent aussi comme contributions, "
                    "à la date du signalement et pour la personne qui les a "
                    "traités. Une contribution compte pour l'organisation "
                    "actuelle de son auteur, pas pour celle du moment où elle "
                    "a été faite. "
                    "Pour les communes, seules les éditions faites depuis le 7 "
                    "juillet 2025 sont comptées : une commune est nouvelle si "
                    "sa première édition depuis cette date tombe dans la "
                    "période. Sur toute la période (days=all), new vaut donc "
                    "total, pour les communes comme pour les organisations. "
                    "Les données sont mises à jour environ "
                    "toutes les heures. Pour afficher plusieurs périodes "
                    "côte à côte, utilisez plutôt "
                    "GET /api/alpha/contributions/summaries/ : des appels "
                    "séparés pendant une mise à jour peuvent renvoyer des "
                    "périodes calculées à des moments différents."
                ),
                "operationId": "getContributionSummary",
                "parameters": [
                    {
                        "name": "days",
                        "in": "query",
                        "description": (
                            "Période : les "
                            + " ou ".join(str(d) for d in WINDOWS_DAYS)
                            + f" derniers jours, ou {ALL_PERIOD} pour toutes les "
                            "contributions depuis toujours (since vaut alors "
                            "null, et new vaut total ; pour les communes, seules "
                            "les éditions faites depuis le 7 juillet 2025 sont "
                            "comptées)."
                        ),
                        "required": False,
                        "schema": {
                            "type": "string",
                            "enum": [str(d) for d in WINDOWS_DAYS] + [ALL_PERIOD],
                            "default": str(DEFAULT_WINDOW_DAYS),
                        },
                    }
                ],
                "responses": {
                    "200": {
                        "description": "La synthèse de la période.",
                        "content": {"application/json": {"schema": SUMMARY_SCHEMA}},
                    }
                },
            }
        }
    )
    def get(self, request: Request) -> Response:
        days_param = request.query_params.get("days", str(DEFAULT_WINDOW_DAYS))
        if days_param == ALL_PERIOD:
            return Response(get_contribution_summary(None))
        if days_param not in [str(d) for d in WINDOWS_DAYS]:
            raise BadRequest(
                detail="Le paramètre days doit valoir "
                + ", ".join(str(d) for d in WINDOWS_DAYS)
                + f" ou {ALL_PERIOD}."
            )
        return Response(get_contribution_summary(int(days_param)))


class ContributionSummariesView(RNBLoggingMixin, APIView):
    """
    GET /api/alpha/contributions/summaries/
    Every period of the contribution summary in one response, all computed at
    the same instant, so that they can be shown side by side.
    """

    @rnb_doc(
        {
            "get": {
                "summary": "Synthèses des contributions, toutes périodes",
                "description": (
                    "Retourne en une seule réponse la synthèse de chaque "
                    "période ("
                    + ", ".join(f"{d} derniers jours" for d in WINDOWS_DAYS)
                    + ", puis depuis toujours), "
                    "au même format que GET /api/alpha/contributions/summary/. "
                    "Les périodes sont toujours calculées au même instant "
                    "(même updated_at). Les données sont mises à jour environ "
                    "toutes les heures."
                ),
                "operationId": "getContributionSummaries",
                "responses": {
                    "200": {
                        "description": (
                            "Les synthèses, de la période la plus courte à la "
                            "plus longue."
                        ),
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "summaries": {
                                            "type": "array",
                                            "items": SUMMARY_SCHEMA,
                                        }
                                    },
                                    "required": ["summaries"],
                                }
                            }
                        },
                    }
                },
            }
        },
        with_400=False,
    )
    def get(self, request: Request) -> Response:
        return Response({"summaries": get_all_contribution_summaries()})


class ContributionRankingsView(RNBLoggingMixin, APIView):
    """
    GET /api/alpha/contributions/rankings/
    Long rankings of every period, for the details page of the summary.
    """

    @rnb_doc(
        {
            "get": {
                "summary": "Classements complets des contributions, toutes périodes",
                "description": (
                    "Retourne, pour chaque période ("
                    + ", ".join(f"{d} derniers jours" for d in WINDOWS_DAYS)
                    + ", puis depuis toujours) : tous les contributeurs (hors "
                    "comptes désactivés) et "
                    "toutes les organisations (selon l'organisation actuelle "
                    "de leurs membres), et les "
                    f"{RANKED_CITIES_LIMIT} communes les plus éditées, les plus "
                    "actifs d'abord. Ce sont les versions longues de top dans "
                    "GET /api/alpha/contributions/summaries/ : quand les deux "
                    "réponses ont le même updated_at, elles viennent du même "
                    "calcul et top est le début de ces listes. Des appels "
                    "séparés pendant une mise à jour peuvent renvoyer des "
                    "calculs différents. Jusqu'en 2025, les signalements "
                    "corrigés comptent aussi comme contributions, à la date du "
                    "signalement et pour la personne qui les a traités. "
                    "Pour les communes, seules les éditions faites depuis le 7 "
                    "juillet 2025 sont comptées. Les données sont mises à jour "
                    "environ toutes les heures."
                ),
                "operationId": "getContributionRankings",
                "responses": {
                    "200": {
                        "description": (
                            "Les classements, de la période la plus courte à "
                            "la plus longue."
                        ),
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "rankings": {
                                            "type": "array",
                                            "items": RANKINGS_SCHEMA,
                                        }
                                    },
                                    "required": ["rankings"],
                                }
                            }
                        },
                    }
                },
            }
        },
        with_400=False,
    )
    def get(self, request: Request) -> Response:
        return Response({"rankings": get_all_contribution_rankings()})
