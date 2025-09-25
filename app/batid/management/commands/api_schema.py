import json

from django.core.management.base import BaseCommand
from openapi_spec_validator import validate
from openapi_spec_validator.validation.exceptions import OpenAPIValidationError

from api_alpha.utils.rnb_doc import build_schema_all_endpoints


class Command(BaseCommand):

    # add a boolean option to validate or note the schema
    def add_arguments(self, parser):
        parser.add_argument("--validate", action="store_true", default=False)

    def handle(self, *args, **options):

        schema_dict = build_schema_all_endpoints()
        print(json.dumps(schema_dict, indent=4, ensure_ascii=False))

        if options["validate"]:

            print("-------- Validate schema --------")
            try:
                validate(schema_dict)
                print("> Schema is valid 🎉")
            except OpenAPIValidationError as e:
                print(f"> Schema is NOT valid: {e}")
                raise e
