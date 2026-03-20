import secrets
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.core import signing
from django.core.cache import cache
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView


# ---------------------------------------------------------------------------
# OIDC utility functions
# ---------------------------------------------------------------------------

def get_oidc_config():
    """Fetch and cache the OIDC discovery document (1h TTL)."""
    cached = cache.get("pro_connect_oidc_config")
    if cached:
        return cached
    resp = requests.get(settings.PRO_CONNECT_DISCOVERY_URL, timeout=10)
    resp.raise_for_status()
    config = resp.json()
    cache.set("pro_connect_oidc_config", config, 3600)
    return config


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

class AuthorizeView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        redirect_uri = request.query_params.get("redirect_uri")
        if not redirect_uri or redirect_uri not in settings.PRO_CONNECT_ALLOWED_REDIRECT_URIS:
            return Response(
                {"error": "invalid_redirect_uri"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        nonce = secrets.token_urlsafe(32)
        state = signing.dumps(
            {"nonce": nonce, "redirect_uri": redirect_uri},
            salt="pro_connect",
        )

        oidc_config = get_oidc_config()
        params = urlencode({
            "response_type": "code",
            "client_id": settings.PRO_CONNECT_CLIENT_ID,
            "redirect_uri": settings.PRO_CONNECT_REDIRECT_URI,
            "scope": settings.PRO_CONNECT_SCOPES,
            "state": state,
            "nonce": nonce,
        })
        authorization_url = f"{oidc_config['authorization_endpoint']}?{params}"

        return Response({"authorization_url": authorization_url})
