import json

from batid.models import EmailNotificationOptOut
from batid.services.email import make_unsubscribe_token
from django.contrib.auth.models import User
from rest_framework.test import APITestCase


class UnsubscribeEndpointTest(APITestCase):
    def test_unsubscribe_with_valid_token(self):
        """
        Input: POST /notifications/unsubscribe with a valid signed token.
        Expected: 200, the email is opted out and returned in the body.
        """
        token = make_unsubscribe_token("reporter@example.com")
        response = self.client.post(
            "/api/alpha/notifications/unsubscribe",
            data=json.dumps({"token": token}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["email"], "reporter@example.com")
        self.assertTrue(EmailNotificationOptOut.is_opted_out("reporter@example.com"))

    def test_unsubscribe_with_tampered_token(self):
        """
        Input: POST /notifications/unsubscribe with a tampered token.
        Expected: 400 and no opt-out row is created.
        """
        token = make_unsubscribe_token("reporter@example.com")
        tampered = token[:-1] + ("a" if token[-1] != "a" else "b")
        response = self.client.post(
            "/api/alpha/notifications/unsubscribe",
            data=json.dumps({"token": tampered}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(EmailNotificationOptOut.objects.count(), 0)

    def test_unsubscribe_without_token(self):
        """
        Input: POST /notifications/unsubscribe with an empty body.
        Expected: 400 (token is required).
        """
        response = self.client.post(
            "/api/alpha/notifications/unsubscribe",
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)


class PreferencesEndpointTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="user", email="user@example.com")

    def test_preferences_requires_authentication(self):
        """
        Input: GET /notifications/preferences while anonymous.
        Expected: 401 or 403 (authentication required).
        """
        response = self.client.get("/api/alpha/notifications/preferences")
        self.assertIn(response.status_code, (401, 403))

    def test_get_preferences_subscribed_by_default(self):
        """
        Input: GET /notifications/preferences for a user that never opted out.
        Expected: 200 with {"subscribed": True}; False once opted out.
        """
        self.client.force_authenticate(user=self.user)
        response = self.client.get("/api/alpha/notifications/preferences")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"subscribed": True})

        EmailNotificationOptOut.opt_out("user@example.com")
        response = self.client.get("/api/alpha/notifications/preferences")
        self.assertEqual(response.json(), {"subscribed": False})

    def test_put_preferences_unsubscribe_then_resubscribe(self):
        """
        Input: PUT subscribed=false then subscribed=true on request.user.email.
        Expected: the opt-out row is created then removed accordingly.
        """
        self.client.force_authenticate(user=self.user)

        response = self.client.put(
            "/api/alpha/notifications/preferences",
            data=json.dumps({"subscribed": False}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"subscribed": False})
        self.assertTrue(EmailNotificationOptOut.is_opted_out("user@example.com"))

        response = self.client.put(
            "/api/alpha/notifications/preferences",
            data=json.dumps({"subscribed": True}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"subscribed": True})
        self.assertFalse(EmailNotificationOptOut.is_opted_out("user@example.com"))
