from unittest import mock

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase
from rest_framework.throttling import ScopedRateThrottle

SECRET = "sandbox-secret-token"


# THROTTLE_RATES is bound to the settings dict at import time, so overriding
# REST_FRAMEWORK would not reach it: patch the rate dict itself. A tiny rate keeps
# the tests to a couple of requests instead of eleven.
@mock.patch.dict(ScopedRateThrottle.THROTTLE_RATES, {"create_user": "1/day"})
@override_settings(SANDBOX_SECRET_TOKEN=SECRET)
@mock.patch("api_alpha.endpoints.auth.create_user.validate_captcha")
class CreateUserThrottleTest(APITestCase):
    """The sandbox signup endpoint is throttled per IP to curb abuse. Production
    mirrors every new account through that same endpoint, from a single IP, so
    those trusted calls are exempt from the throttle. The exemption requires both
    the shared secret and the sandbox environment."""

    def setUp(self):
        Group.objects.get_or_create(name=settings.CONTRIBUTORS_GROUP_NAME)
        # ScopedRateThrottle counts through the default cache: start from scratch.
        cache.clear()

    def _signup(self, index, auth=None):
        headers = {"HTTP_AUTHORIZATION": auth} if auth else {}
        return self.client.post(
            "/api/alpha/auth/users/",
            {
                "first_name": "Test",
                "last_name": "User",
                "email": f"user{index}@example.test",
                "username": f"user{index}",
                "password": "Str0ng-Passw0rd-9x!",
            },
            **headers,
        )

    @override_settings(ENVIRONMENT="sandbox")
    def test_public_signups_are_throttled(self, _mock_captcha):
        """Without the shared secret, the second signup from the same IP is
        rejected with 429."""
        self.assertEqual(self._signup(1).status_code, 201)
        self.assertEqual(self._signup(2).status_code, 429)

    @override_settings(ENVIRONMENT="sandbox")
    def test_trusted_mirroring_calls_are_not_throttled(self, _mock_captcha):
        """Carrying the shared secret on the sandbox, repeated creations all go
        through: this is how production mirrors its accounts."""
        for index in range(3):
            response = self._signup(index, auth=f"Bearer {SECRET}")
            self.assertEqual(response.status_code, 201)

    @override_settings(ENVIRONMENT="sandbox")
    def test_wrong_secret_is_still_throttled(self, _mock_captcha):
        """A wrong bearer token grants no exemption."""
        self.assertEqual(self._signup(1, auth="Bearer nope").status_code, 201)
        self.assertEqual(self._signup(2, auth="Bearer nope").status_code, 429)

    @override_settings(ENVIRONMENT="production")
    def test_exemption_does_not_apply_outside_sandbox(self, _mock_captcha):
        """The exemption is scoped to the sandbox: on production the secret does
        not lift the public signup throttle."""
        self.assertEqual(self._signup(1, auth=f"Bearer {SECRET}").status_code, 201)
        self.assertEqual(self._signup(2, auth=f"Bearer {SECRET}").status_code, 429)
