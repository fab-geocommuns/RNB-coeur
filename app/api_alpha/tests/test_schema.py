from api_alpha.utils.rnb_doc import (
    build_schema_all_endpoints,
    build_schema_ogc_endpoints,
)
from django.test import TestCase
from openapi_spec_validator import validate
from openapi_spec_validator.validation.exceptions import OpenAPIValidationError
from rest_framework.test import APITestCase


class OpenAPISchemaEndpoint(APITestCase):
    def test_endpoint(self):

        # We HEAD insted of GET to avoir downloading the whole file
        r = self.client.head("/api/alpha/schema/")
        self.assertEqual(r.status_code, 200)

        # check the the response is a yml file
        self.assertEqual(r["Content-Type"], "application/x-yaml")


class OpenAPISchemes(TestCase):
    def test_all_endpoints_schema(self):

        schema = build_schema_all_endpoints()

        # assert it does not raise an exception
        try:
            validate(schema)
        except OpenAPIValidationError as e:
            self.fail(f"All endpoints schema is not valid: {e}")

    def test_ogc_endpoints_schema(self):

        schema = build_schema_ogc_endpoints()

        # assert it does not raise an exception
        try:
            validate(schema)
        except OpenAPIValidationError as e:
            self.fail(f"OGC schema is not valid: {e}")

    def test_mfa_management_endpoints_are_documented(self):
        """All endpoints schema: the status, replacement and backup codes paths of
        the second factor are documented."""
        paths = build_schema_all_endpoints()["paths"]

        for path in (
            "/api/alpha/auth/mfa/status/",
            "/api/alpha/auth/mfa/replace/setup/",
            "/api/alpha/auth/mfa/replace/confirm/",
            "/api/alpha/auth/mfa/backup_codes/",
        ):
            self.assertIn(path, paths)
