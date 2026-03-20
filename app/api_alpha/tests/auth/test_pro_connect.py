from unittest import mock
from urllib.parse import parse_qs
from urllib.parse import urlparse

from django.core import signing
from django.test import override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from batid.models import ProConnectIdentity
from batid.tests.factories.users import ContributorUserFactory

FAKE_OIDC_CONFIG = {
    "authorization_endpoint": "https://proconnect.example/authorize",
    "token_endpoint": "https://proconnect.example/token",
    "userinfo_endpoint": "https://proconnect.example/userinfo",
    "end_session_endpoint": "https://proconnect.example/logout",
    "jwks_uri": "https://proconnect.example/jwks",
}


@override_settings(
    PRO_CONNECT_CLIENT_ID="test-client-id",
    PRO_CONNECT_REDIRECT_URI="http://localhost:8000/api/alpha/auth/pro_connect/callback/",
    PRO_CONNECT_SCOPES="openid email given_name usual_name",
    PRO_CONNECT_ALLOWED_REDIRECT_URIS=["http://localhost:3000"],
)
class AuthorizeTest(APITestCase):
    """GET /authorize/ returns an authorization URL with state containing nonce and redirect_uri."""

    @mock.patch(
        "api_alpha.endpoints.auth.pro_connect.get_oidc_config",
        return_value=FAKE_OIDC_CONFIG,
    )
    def test_authorize_returns_authorization_url(self, mock_config):
        response = self.client.get(
            "/api/alpha/auth/pro_connect/authorize/",
            {"redirect_uri": "http://localhost:3000"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("authorization_url", data)
        self.assertIn("proconnect.example/authorize", data["authorization_url"])
        self.assertIn("state=", data["authorization_url"])

        # Verify state is decodable and contains nonce + redirect_uri
        parsed = urlparse(data["authorization_url"])
        params = parse_qs(parsed.query)
        state = params["state"][0]
        payload = signing.loads(state, salt="pro_connect", max_age=300)
        self.assertIn("nonce", payload)
        self.assertIn("redirect_uri", payload)
        self.assertEqual(payload["redirect_uri"], "http://localhost:3000")

    @mock.patch(
        "api_alpha.endpoints.auth.pro_connect.get_oidc_config",
        return_value=FAKE_OIDC_CONFIG,
    )
    def test_authorize_rejects_invalid_redirect_uri(self, mock_config):
        """Authorize rejects redirect_uri not in allowlist → 400."""
        response = self.client.get(
            "/api/alpha/auth/pro_connect/authorize/",
            {"redirect_uri": "https://evil.com"},
        )
        self.assertEqual(response.status_code, 400)

    @mock.patch(
        "api_alpha.endpoints.auth.pro_connect.get_oidc_config",
        return_value=FAKE_OIDC_CONFIG,
    )
    def test_authorize_rejects_missing_redirect_uri(self, mock_config):
        """Authorize rejects missing redirect_uri → 400."""
        response = self.client.get("/api/alpha/auth/pro_connect/authorize/")
        self.assertEqual(response.status_code, 400)
