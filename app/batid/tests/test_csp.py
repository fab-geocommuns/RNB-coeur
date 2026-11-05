import io
from unittest import mock

import revproxy.views  # type: ignore[import-untyped]
from django.contrib.auth.models import User
from django.test import TestCase
from urllib3.response import HTTPResponse

CSP_HEADER = "Content-Security-Policy"


def upstream_response(*, headers=None):
    return HTTPResponse(
        body=io.BytesIO(b"<html></html>"),
        headers={"Content-Type": "text/html", **(headers or {})},
        status=200,
        preload_content=False,
    )


class CspHeaderTest(TestCase):
    def test_home_page_has_csp(self):
        """
        Input: GET on the home page.
        Expected: the CSP header blocks inline scripts, plugins, framing and
        sources other than the site itself by default.
        """
        response = self.client.get("/")

        csp = response[CSP_HEADER]
        self.assertIn("default-src 'self'", csp)
        self.assertIn("object-src 'none'", csp)
        self.assertIn("frame-ancestors 'none'", csp)
        # Scripts fall back to default-src: only 'self', no inline script.
        self.assertNotIn("script-src", csp)

    def test_admin_login_has_csp(self):
        """
        Input: GET on the admin login page.
        Expected: the CSP header is set, with form submissions limited to the site.
        """
        response = self.client.get("/admin/login/")

        self.assertIn("form-action 'self'", response[CSP_HEADER])


@mock.patch.object(revproxy.views.HTTP_POOLS, "urlopen")
class CspProxyTest(TestCase):
    def test_metabase_keeps_its_own_csp(self, urlopen):
        """
        Input: a public Metabase dashboard whose upstream response has its own CSP.
        Expected: the browser gets Metabase's CSP, not the API's.
        """
        urlopen.return_value = upstream_response(
            headers={CSP_HEADER: "default-src 'self' metabase"}
        )

        response = self.client.get("/metabase/public/dashboard/abc")

        self.assertEqual(response[CSP_HEADER], "default-src 'self' metabase")

    def test_metabase_without_csp_gets_none(self, urlopen):
        """
        Input: a public Metabase dashboard whose upstream response has no CSP.
        Expected: no CSP header is added.
        """
        urlopen.return_value = upstream_response()

        response = self.client.get("/metabase/public/dashboard/abc")

        self.assertNotIn(CSP_HEADER, response)

    def test_flower_gets_no_csp(self, urlopen):
        """
        Input: a superuser opens Flower, whose upstream response has no CSP.
        Expected: no CSP header is added.
        """
        user = User.objects.create_superuser("admin", "admin@example.com", "pwd")
        self.client.force_login(user)
        urlopen.return_value = upstream_response()

        response = self.client.get("/flower/")

        self.assertNotIn(CSP_HEADER, response)
