from django.test import TestCase
from openapi_spec_validator import validate
from openapi_spec_validator.validation.exceptions import OpenAPIValidationError
from rest_framework.test import APITestCase

from api_alpha.utils.rnb_doc import (
    build_schema_all_endpoints,
    build_schema_ogc_endpoints,
)


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
