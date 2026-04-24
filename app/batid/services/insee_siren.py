import requests
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from batid.exceptions import INSEESireneAPIDown

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

    if response.status_code == 404:
        return None

    if response.status_code == 200:
        return response.json()

    raise INSEESireneAPIDown()


def extract_org_name(siren_org: dict) -> str:
    periods = siren_org.get("periodesUniteLegale", [])
    current = next(
        (p for p in periods if p.get("dateFin") is None),
        {},
    )
    return current.get("denominationUniteLegale") or ""
