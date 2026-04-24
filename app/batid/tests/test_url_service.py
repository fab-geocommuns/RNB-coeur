from urllib.parse import parse_qs
from urllib.parse import urlparse

from django.test import SimpleTestCase

from batid.services.url import add_params_to_url


class AddParamsToUrlTest(SimpleTestCase):
    def test_without_previous_params(self):
        """
        Input: plain URL with no query string. Expected: params appended after '?'.
        """

        new_url = add_params_to_url("http://localhost:3000/callback", {"token": "abc"})

        self.assertEqual(new_url, "http://localhost:3000/callback?token=abc")

    def test_with_existing_params(self):
        """
        Input: URL already containing ?redirect=http://foo.com.
        Expected: new params appended with '&', exactly one '?', and redirect value intact.
        """
        new_url = add_params_to_url(
            "http://localhost:3000/callback?redirect=http%3A%2F%2Ffoo.com",
            {"token": "abc", "user_id": "1"},
        )

        self.assertEqual(new_url.count("?"), 1)

        params = parse_qs(urlparse(new_url).query)

        self.assertEqual(params["redirect"], ["http://foo.com"])
        self.assertEqual(params["token"], ["abc"])
        self.assertEqual(params["user_id"], ["1"])

    def test_empty_params_returns_url_unchanged(self):
        """Input: empty params dict. Expected: URL returned as-is."""
        new_url = add_params_to_url("http://localhost:3000/callback", {})
        self.assertEqual(new_url, "http://localhost:3000/callback")
