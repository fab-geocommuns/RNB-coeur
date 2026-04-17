from unittest import mock
from urllib.parse import parse_qs, urlparse

from batid.models import ProConnectIdentity
from batid.tests.factories.users import ContributorUserFactory
from django.core import signing
from django.test import override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

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


FAKE_JWKS = {"keys": [{"kty": "RSA", "kid": "test-key", "n": "fake", "e": "AQAB"}]}

FAKE_USERINFO = {
    "sub": "pro-connect-sub-123",
    "email": "agent@gouv.fr",
    "given_name": "Marie",
    "usual_name": "Dupont",
    "siret": "13002526500013",
}


def _make_state(redirect_uri="http://localhost:3000", nonce="test-nonce"):
    return signing.dumps(
        {"nonce": nonce, "redirect_uri": redirect_uri},
        salt="pro_connect",
    )


@override_settings(
    PRO_CONNECT_CLIENT_ID="test-client-id",
    PRO_CONNECT_CLIENT_SECRET="test-client-secret",
    PRO_CONNECT_REDIRECT_URI="http://localhost:8000/api/alpha/auth/pro_connect/callback/",
    PRO_CONNECT_SCOPES="openid email given_name usual_name",
    PRO_CONNECT_ALLOWED_REDIRECT_URIS=["http://localhost:3000"],
    CONTRIBUTORS_GROUP_NAME="Contributors",
    FRONTEND_URL="http://localhost:3000",
)
@mock.patch(
    "batid.services.organization.fetch_siren_data",
    return_value=None,
)
class CallbackTest(APITestCase):
    def _call_callback(self, code="auth-code", state=None):
        if state is None:
            state = _make_state()
        return self.client.get(
            "/api/alpha/auth/pro_connect/callback/",
            {"code": code, "state": state},
        )

    @mock.patch(
        "api_alpha.endpoints.auth.pro_connect.fetch_userinfo",
        return_value=FAKE_USERINFO,
    )
    @mock.patch(
        "api_alpha.endpoints.auth.pro_connect.verify_id_token",
        return_value={"nonce": "test-nonce"},
    )
    @mock.patch(
        "api_alpha.endpoints.auth.pro_connect.exchange_code_for_tokens",
        return_value=("fake-access-token", "fake-id-token"),
    )
    def test_callback_creates_new_user(
        self, mock_exchange, mock_verify, mock_userinfo, mock_siren
    ):
        """Callback with unknown sub and email creates User + UserProfile + ProConnectIdentity + Token + Contributors group."""
        from django.contrib.auth.models import Group, User

        Group.objects.get_or_create(name="Contributors")

        response = self._call_callback()

        self.assertEqual(response.status_code, 302)
        self.assertIn("token=", response.url)
        self.assertIn("http://localhost:3000", response.url)

        user = User.objects.get(email="agent@gouv.fr")
        self.assertTrue(user.is_active)
        self.assertFalse(user.has_usable_password())
        self.assertEqual(user.first_name, "Marie")
        self.assertEqual(user.last_name, "Dupont")
        self.assertTrue(user.groups.filter(name="Contributors").exists())
        self.assertTrue(hasattr(user, "profile"))
        self.assertTrue(hasattr(user, "pro_connect"))
        self.assertEqual(user.pro_connect.sub, "pro-connect-sub-123")
        self.assertEqual(user.pro_connect.siret, "13002526500013")
        self.assertTrue(Token.objects.filter(user=user).exists())

    @mock.patch(
        "api_alpha.endpoints.auth.pro_connect.fetch_userinfo",
        return_value=FAKE_USERINFO,
    )
    @mock.patch(
        "api_alpha.endpoints.auth.pro_connect.verify_id_token",
        return_value={"nonce": "test-nonce"},
    )
    @mock.patch(
        "api_alpha.endpoints.auth.pro_connect.exchange_code_for_tokens",
        return_value=("fake-access-token", "fake-id-token"),
    )
    def test_callback_links_existing_user_by_email(
        self, mock_exchange, mock_verify, mock_userinfo, mock_siren
    ):
        """Callback with unknown sub but known email links ProConnectIdentity to existing user."""
        from django.contrib.auth.models import Group, User

        Group.objects.get_or_create(name="Contributors")
        existing_user = User.objects.create_user(
            username="existing",
            email="agent@gouv.fr",
            password="testpass123",
            is_active=True,
        )

        response = self._call_callback()

        self.assertEqual(response.status_code, 302)
        existing_user.refresh_from_db()
        self.assertTrue(hasattr(existing_user, "pro_connect"))
        self.assertEqual(existing_user.pro_connect.sub, "pro-connect-sub-123")
        # User keeps their password
        self.assertTrue(existing_user.has_usable_password())

    @mock.patch(
        "api_alpha.endpoints.auth.pro_connect.fetch_userinfo",
        return_value=FAKE_USERINFO,
    )
    @mock.patch(
        "api_alpha.endpoints.auth.pro_connect.verify_id_token",
        return_value={"nonce": "test-nonce"},
    )
    @mock.patch(
        "api_alpha.endpoints.auth.pro_connect.exchange_code_for_tokens",
        return_value=("fake-access-token", "fake-id-token"),
    )
    def test_callback_links_inactive_account_activates_and_removes_password(
        self, mock_exchange, mock_verify, mock_userinfo
    ):
        """Callback with unknown sub but known email matching an inactive account:
        links ProConnectIdentity, activates the account, and removes the password."""
        from django.contrib.auth.models import Group, User

        Group.objects.get_or_create(name="Contributors")
        existing_user = User.objects.create_user(
            username="existing",
            email="agent@gouv.fr",
            password="testpass123",
            is_active=False,
        )

        response = self._call_callback()

        self.assertEqual(response.status_code, 302)
        existing_user.refresh_from_db()
        self.assertTrue(hasattr(existing_user, "pro_connect"))
        self.assertEqual(existing_user.pro_connect.sub, "pro-connect-sub-123")
        self.assertTrue(existing_user.is_active)
        self.assertFalse(existing_user.has_usable_password())

    @mock.patch(
        "api_alpha.endpoints.auth.pro_connect.fetch_userinfo",
        return_value=FAKE_USERINFO,
    )
    @mock.patch(
        "api_alpha.endpoints.auth.pro_connect.verify_id_token",
        return_value={"nonce": "test-nonce"},
    )
    @mock.patch(
        "api_alpha.endpoints.auth.pro_connect.exchange_code_for_tokens",
        return_value=("fake-access-token", "fake-id-token"),
    )
    def test_callback_returns_existing_pro_connect_user(
        self, mock_exchange, mock_verify, mock_userinfo, mock_siren
    ):
        """Callback with known sub updates User fields and last_id_token."""
        from django.contrib.auth.models import Group, User

        Group.objects.get_or_create(name="Contributors")
        user = User.objects.create_user(
            username="existing",
            email="agent@gouv.fr",
            password="testpass123",
            first_name="Old",
            last_name="Name",
        )
        ProConnectIdentity.objects.create(
            user=user,
            sub="pro-connect-sub-123",
            last_id_token="old-token",
            siret="00000000000000",
        )

        response = self._call_callback()

        self.assertEqual(response.status_code, 302)
        user.refresh_from_db()
        self.assertEqual(user.first_name, "Marie")
        self.assertEqual(user.last_name, "Dupont")
        self.assertEqual(user.pro_connect.last_id_token, "fake-id-token")
        self.assertEqual(
            user.pro_connect.siret, "13002526500013"
        )  # siret is updated from userinfo

    @mock.patch(
        "api_alpha.endpoints.auth.pro_connect.fetch_userinfo",
        return_value=FAKE_USERINFO,
    )
    @mock.patch(
        "api_alpha.endpoints.auth.pro_connect.verify_id_token",
        return_value={"nonce": "test-nonce"},
    )
    @mock.patch(
        "api_alpha.endpoints.auth.pro_connect.exchange_code_for_tokens",
        return_value=("fake-access-token", "fake-id-token"),
    )
    def test_callback_updates_last_login(
        self, mock_exchange, mock_verify, mock_userinfo, mock_siren
    ):
        """Successful callback sets last_login on the authenticated user."""
        from django.contrib.auth.models import Group, User

        Group.objects.get_or_create(name="Contributors")

        self._call_callback()

        user = User.objects.get(email="agent@gouv.fr")
        self.assertIsNotNone(user.last_login)

    @mock.patch(
        "api_alpha.endpoints.auth.pro_connect.fetch_userinfo",
        return_value=FAKE_USERINFO,
    )
    @mock.patch(
        "api_alpha.endpoints.auth.pro_connect.verify_id_token",
        return_value={"nonce": "test-nonce"},
    )
    @mock.patch(
        "api_alpha.endpoints.auth.pro_connect.exchange_code_for_tokens",
        return_value=("fake-access-token", "fake-id-token"),
    )
    def test_callback_rejects_disabled_user(
        self, mock_exchange, mock_verify, mock_userinfo, mock_siren
    ):
        """Callback for a disabled user (is_active=False) redirects with account_disabled error."""
        from django.contrib.auth.models import User

        user = User.objects.create_user(
            username="disabled", email="agent@gouv.fr", is_active=False
        )
        ProConnectIdentity.objects.create(
            user=user, sub="pro-connect-sub-123", last_id_token="old-token"
        )

        response = self._call_callback()

        self.assertEqual(response.status_code, 302)
        self.assertIn("error=account_disabled", response.url)
        self.assertNotIn("token=", response.url)

    def test_callback_invalid_state(self, mock_siren):
        """Callback with tampered state redirects with error."""
        response = self._call_callback(state="tampered-state")

        self.assertEqual(response.status_code, 302)
        self.assertIn("error=", response.url)

    @mock.patch(
        "api_alpha.endpoints.auth.pro_connect.fetch_userinfo",
        return_value={
            "sub": "pro-connect-sub-123",
            "email": "agent@gouv.fr",
            "given_name": "Marie",
            "usual_name": "Dupont",
        },
    )
    @mock.patch(
        "api_alpha.endpoints.auth.pro_connect.verify_id_token",
        return_value={"nonce": "test-nonce"},
    )
    @mock.patch(
        "api_alpha.endpoints.auth.pro_connect.exchange_code_for_tokens",
        return_value=("fake-access-token", "fake-id-token"),
    )
    def test_callback_without_siret_claim_stores_empty_string(
        self, mock_exchange, mock_verify, mock_userinfo, mock_siren
    ):
        """Input: userinfo with no siret claim. Expected: ProConnectIdentity is still created with siret as empty string (claim is optional)."""
        from django.contrib.auth.models import Group, User

        Group.objects.get_or_create(name="Contributors")

        self._call_callback()

        user = User.objects.get(email="agent@gouv.fr")
        self.assertEqual(user.pro_connect.siret, "")


@override_settings(
    PRO_CONNECT_POST_LOGOUT_REDIRECT_URI="http://localhost:8000/api/alpha/auth/pro_connect/logout/callback/",
    PRO_CONNECT_ALLOWED_REDIRECT_URIS=["http://localhost:3000"],
)
class LogoutTest(APITestCase):
    @mock.patch(
        "api_alpha.endpoints.auth.pro_connect.get_oidc_config",
        return_value=FAKE_OIDC_CONFIG,
    )
    def test_logout_redirects_to_pro_connect(self, mock_config):
        """Authenticated user with ProConnectIdentity → redirect 302 to Pro Connect end_session_endpoint."""
        user = ContributorUserFactory(is_active=True)
        ProConnectIdentity.objects.create(
            user=user, sub="sub-123", last_id_token="the-id-token"
        )
        token = Token.objects.get(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        response = self.client.get(
            "/api/alpha/auth/pro_connect/logout/",
            {"post_logout_redirect_uri": "http://localhost:3000"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("proconnect.example/logout", response.url)
        self.assertIn("id_token_hint=the-id-token", response.url)
        self.assertIn("state=", response.url)

    def test_logout_without_pro_connect_identity(self):
        """Authenticated user without ProConnectIdentity → 400."""
        user = ContributorUserFactory(is_active=True)
        token = Token.objects.get(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        response = self.client.get(
            "/api/alpha/auth/pro_connect/logout/",
            {"post_logout_redirect_uri": "http://localhost:3000"},
        )

        self.assertEqual(response.status_code, 400)


class LogoutCallbackTest(APITestCase):
    def test_logout_callback_redirects_to_frontend(self):
        """Logout callback with valid state → redirect 302 to frontend post_logout_redirect_uri."""
        state = signing.dumps(
            {"post_logout_redirect_uri": "http://localhost:3000"},
            salt="pro_connect_logout",
        )

        response = self.client.get(
            "/api/alpha/auth/pro_connect/logout/callback/",
            {"state": state},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "http://localhost:3000")

    def test_logout_callback_invalid_state(self):
        """Logout callback with tampered state → 400."""
        response = self.client.get(
            "/api/alpha/auth/pro_connect/logout/callback/",
            {"state": "tampered"},
        )

        self.assertEqual(response.status_code, 400)
