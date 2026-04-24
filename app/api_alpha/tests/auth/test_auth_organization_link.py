from unittest import mock

from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.test import override_settings
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from api_alpha.tests.auth.test_pro_connect import _make_state
from api_alpha.tests.auth.test_pro_connect import FAKE_OIDC_CONFIG
from api_alpha.tests.auth.test_pro_connect import FAKE_USERINFO
from batid.models import Organization
from batid.models import ProConnectIdentity
from batid.models import UserProfile


@override_settings(
    PRO_CONNECT_CLIENT_ID="test-client-id",
    PRO_CONNECT_CLIENT_SECRET="test-client-secret",
    PRO_CONNECT_REDIRECT_URI="http://localhost:8000/api/alpha/auth/pro_connect/callback/",
    PRO_CONNECT_SCOPES="openid email given_name usual_name",
    PRO_CONNECT_ALLOWED_REDIRECT_URIS=["http://localhost:3000"],
)
@mock.patch("batid.services.organization.fetch_siren_data", return_value=None)
@mock.patch(
    "api_alpha.endpoints.auth.pro_connect.fetch_userinfo", return_value=FAKE_USERINFO
)
@mock.patch(
    "api_alpha.endpoints.auth.pro_connect.verify_id_token",
    return_value={"nonce": "test-nonce"},
)
@mock.patch(
    "api_alpha.endpoints.auth.pro_connect.exchange_code_for_tokens",
    return_value=("access-123", "id-token-abc"),
)
class ProConnectOrgLinkTest(APITestCase):
    """ProConnect callback adds user to matching org via Organization.users M2M.

    FAKE_USERINFO["siret"] = "13002526500013" -> SIREN = "130025265".
    Expected: after callback, user belongs to the matching org.
    Inactive users must not be linked.
    """

    def _do_callback(self):
        return self.client.get(
            "/api/alpha/auth/pro_connect/callback/",
            {"code": "auth-code", "state": _make_state()},
        )

    def test_new_user_linked_to_org_via_siren(
        self, _mock_exchange, _mock_verify, _mock_userinfo, _mock_siren
    ):
        """New active user created via ProConnect is added to org.users."""
        org = Organization.objects.create(name="DINUM", siren="130025265")

        response = self._do_callback()

        self.assertEqual(response.status_code, 302)
        user = User.objects.get(email=FAKE_USERINFO["email"])
        self.assertTrue(org.user_profiles.filter(user=user).exists())

    def test_returning_user_org_updated_on_login(
        self, _mock_exchange, _mock_verify, _mock_userinfo, _mock_siren
    ):
        """
        Returning active user (known sub) is added to org.users on login.
        - We create a user without org membership, with a ProConnectIdentity with the right SIRET.
        - On callback, we expect the user to be in the matching org.
        """
        user = User.objects.create(username="marie", email=FAKE_USERINFO["email"])
        UserProfile.objects.create(user=user)
        Token.objects.create(user=user)
        ProConnectIdentity.objects.create(
            user=user,
            sub=FAKE_USERINFO["sub"],
            last_id_token="old-token",
            siret=FAKE_USERINFO["siret"],
        )
        org = Organization.objects.create(name="DINUM", siren="130025265")

        response = self._do_callback()

        self.assertEqual(response.status_code, 302)
        self.assertTrue(org.user_profiles.filter(user=user).exists())

    def test_inactive_user_is_not_linked_to_org(
        self, _mock_exchange, _mock_verify, _mock_userinfo, _mock_siren
    ):
        """Disabled user (is_active=False) is redirected with error and not added to org."""
        org = Organization.objects.create(name="DINUM", siren="130025265")
        user = User.objects.create(
            username="marie",
            email=FAKE_USERINFO["email"],
            is_active=False,
        )
        UserProfile.objects.create(user=user)
        Token.objects.create(user=user)
        ProConnectIdentity.objects.create(
            user=user,
            sub=FAKE_USERINFO["sub"],
            last_id_token="old-token",
            siret=FAKE_USERINFO["siret"],
        )

        response = self._do_callback()

        self.assertIn("account_disabled", response["Location"])
        self.assertFalse(org.user_profiles.filter(user=user).exists())


@override_settings(FRONTEND_URL="http://localhost:3000")
class ActivateUserOrgLinkTest(APITestCase):
    """ActivateUser adds user to org via email domain on activation.

    Inputs: inactive user, valid activation token, Organization with matching email_domain.
    Expected: after GET /auth/activate/..., user is in org.users.
    """

    def test_activation_links_user_to_org_via_email_domain(self):
        user = User.objects.create(
            username="newuser", email="agent@gouv.fr", is_active=False
        )
        UserProfile.objects.create(user=user)
        token = default_token_generator.make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        org = Organization.objects.create(name="Etat", email_domain="gouv.fr")

        self.client.get(f"/api/alpha/auth/activate/{uid}/{token}/")

        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertTrue(org.user_profiles.filter(user=user).exists())
