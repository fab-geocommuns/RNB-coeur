import requests
from batid.exceptions import INSEESireneAPIDown
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from batid.exceptions import INSEESireneAPIDown
from batid.exceptions import INSEESireneAPIForbiddenUnit
from batid.exceptions import INSEESireneAPITooManyRequests
from batid.exceptions import INSEESireneAPIUnknownCode

_BASE_URL = "https://api.insee.fr/api-sirene/3.11"


def fetch_siren_data(siren: str) -> dict | None:
    api_key = settings.INSEE_SIRENE_API_KEY
    if not api_key:
        raise ImproperlyConfigured("INSEE_SIRENE_API_KEY is not configured")

    response = requests.get(
        f"{_BASE_URL}/siren/{siren}",
        headers={
            "X-INSEE-Api-Key-Integration": api_key,
            "Accept": "application/json",
        },
        timeout=5,
    )

    if response.status_code in (301, 404):
        return None

    if response.status_code == 200:
        return response.json()

    if response.status_code == 403:
        raise INSEESireneAPIForbiddenUnit()

    if response.status_code == 429:
        raise INSEESireneAPITooManyRequests()

    if 500 <= response.status_code < 600:
        raise INSEESireneAPIDown()

    raise INSEESireneAPIUnknownCode()


def extract_org_name(siren_org: dict) -> str:
    periods = siren_org.get("periodesUniteLegale", [])
    current = next(
        (p for p in periods if p.get("dateFin") is None),
        {},
    )
    return current.get("denominationUniteLegale") or ""
