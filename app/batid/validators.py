import jsonschema # type: ignore[import-untyped]
from django.core.exceptions import ValidationError
from django.utils.dateparse import parse_datetime
from django.utils.deconstruct import deconstructible
from django.utils.translation import gettext_lazy as _


def validate_many_ext_ids(ext_ids):
    # validate there are keys: source, source_version, id, created_at. source_version is optionnal. No other key must be present
    for ext_id in ext_ids:
        validate_one_ext_id(ext_id)


def validate_one_ext_id(ext_id):
    if "source" not in ext_id:
        raise ValidationError(
            _("External id must have a source key"),
        )

    if not isinstance(ext_id["source"], str):
        raise ValidationError(
            _("External id source must be a str"),
        )

    if (
        "source_version" in ext_id
        and ext_id["source_version"] is not None
        and not isinstance(ext_id["source_version"], str)
    ):
        raise ValidationError(
            _("External id source_version must be a str or None"),
        )

    if "id" not in ext_id:
        raise ValidationError(
            _("External id must have a id key"),
        )

    if not isinstance(ext_id["id"], str):
        raise ValidationError(
            _("External id id must be a str"),
        )

    if "created_at" not in ext_id:
        raise ValidationError(
            _("External id must have a created_at key"),
        )

    if not parse_datetime(ext_id["created_at"]):
        raise ValidationError(
            _("External id created_at date must be a valid formatted date"),
        )


@deconstructible
class JSONSchemaValidator:
    def __init__(self, schema):
        self.schema = schema

    def __call__(self, value):
        try:
            jsonschema.validate(value, self.schema)
        except jsonschema.exceptions.ValidationError as e:
            raise ValidationError(
                "%(value)s must adhere to JSON schema: %(error)s",
                params={"value": value, "error": e},
            )

    def __eq__(self, other):
        return isinstance(other, JSONSchemaValidator) and self.schema == other.schema
