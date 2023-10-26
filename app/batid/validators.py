from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
import datetime


def validate_ext_ids(ext_ids):
    # validate there are keys: source, source_version, id, created_at. source_version is optionnal. No other key must be present
    for ext_id in ext_ids:
        if "source" not in ext_id:
            raise ValidationError(
                _("External id must have a source key"),
            )

        if "source_version" not in ext_id:
            raise ValidationError(
                _("External id must have a source_version key"),
            )

        if "id" not in ext_id:
            raise ValidationError(
                _("External id must have a id key"),
            )

        if "created_at" not in ext_id:
            raise ValidationError(
                _("External id must have a created_at key"),
            )

        try:
            datetime.date.fromisoformat(ext_id["created_at"])
        except ValueError:
            raise ValidationError(
                _(
                    "External id created_at must be a valid ISO 8601 or YYYY-MM-DD formatted date"
                ),
            )
