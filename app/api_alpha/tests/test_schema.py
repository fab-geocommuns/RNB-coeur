from django.test import TestCase
from openapi_spec_validator import validate
from openapi_spec_validator.validation.exceptions import OpenAPIValidationError
from rest_framework.test import APITestCase

from api_alpha.utils.rnb_doc import build_schema_dict


class OpenAPISchemaEndpoint(APITestCase):
    def test_endpoint(self):

        # We HEAD insted of GET to avoir downloading the whole file
        r = self.client.head("/api/alpha/schema/")
        self.assertEqual(r.status_code, 200)

        # check the the response is a yml file
        self.assertEqual(r["Content-Type"], "application/x-yaml")


class OpenAPISchema(TestCase):
    def test_schema(self):

        schema = build_schema_dict()

        # assert it does not raise an exception
        try:
            validate(schema)
        except OpenAPIValidationError as e:
            self.fail(f"Schema is not valid: {e}")
