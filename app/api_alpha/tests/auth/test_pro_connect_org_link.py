from unittest import mock

from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.test import override_settings
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from batid.models import Organization, ProConnectIdentity, UserProfile

from api_alpha.tests.auth.test_pro_connect import (
    FAKE_OIDC_CONFIG,
    FAKE_USERINFO,
    _make_state,
)


@override_settings(
    PRO_CONNECT_CLIENT_ID="test-client-id",
    PRO_CONNECT_CLIENT_SECRET="test-client-secret",
    PRO_CONNECT_REDIRECT_URI="http://localhost:8000/api/alpha/auth/pro_connect/callback/",
    PRO_CONNECT_SCOPES="openid email given_name usual_name",
    PRO_CONNECT_ALLOWED_REDIRECT_URIS=["http://localhost:3000"],
)
@mock.patch("batid.services.organization.fetch_siren_data", return_value=None)
class ProConnectOrgLinkTest(APITestCase):
    """ProConnect callback sets user.profile.organization to matching org.

    FAKE_USERINFO["siret"] = "13002526500013" -> SIREN = "130025265".
    Expected: after callback, user.profile.organization equals the matching org.
    Inactive users must not be linked.
    """

    def _do_callback(self, *args):
        with mock.patch.multiple(
            "api_alpha.endpoints.auth.pro_connect",
            get_oidc_config=mock.DEFAULT,
            exchange_code_for_tokens=mock.DEFAULT,
            verify_id_token=mock.DEFAULT,
            fetch_userinfo=mock.DEFAULT,
        ) as mocks:
            mocks["get_oidc_config"].return_value = FAKE_OIDC_CONFIG
            mocks["exchange_code_for_tokens"].return_value = (
                "access-123",
                "id-token-abc",
            )
            mocks["verify_id_token"].return_value = {"nonce": "test-nonce"}
            mocks["fetch_userinfo"].return_value = FAKE_USERINFO
            return self.client.get(
                "/api/alpha/auth/pro_connect/callback/",
                {"code": "auth-code", "state": _make_state()},
            )

    def test_new_user_profile_linked_to_org_via_siren(self, _mock_siren):
        """New active user created via ProConnect has profile.organization set."""
        org = Organization.objects.create(name="DINUM", siren="130025265")

        response = self._do_callback()

        self.assertEqual(response.status_code, 302)
        user = User.objects.get(email=FAKE_USERINFO["email"])
        self.assertEqual(user.profile.organization, org)

    def test_returning_user_profile_org_updated_on_login(self, _mock_siren):
        """Returning active user (known sub) has profile.organization updated on login."""
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
        user.profile.refresh_from_db()
        self.assertEqual(user.profile.organization, org)

    def test_inactive_user_is_not_linked_to_org(self, _mock_siren):
        """Disabled user (is_active=False) is redirected with error and not linked."""
        Organization.objects.create(name="DINUM", siren="130025265")
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
        user.profile.refresh_from_db()
        self.assertIsNone(user.profile.organization)


@override_settings(FRONTEND_URL="http://localhost:3000")
class ActivateUserOrgLinkTest(APITestCase):
    """ActivateUser sets profile.organization via email domain on activation.

    Inputs: inactive user, valid activation token, Organization with matching email_domain.
    Expected: after GET /auth/activate/..., user.profile.organization is that org.
    """

    def test_activation_links_user_profile_to_org_via_email_domain(self):
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
        user.profile.refresh_from_db()
        self.assertEqual(user.profile.organization, org)
