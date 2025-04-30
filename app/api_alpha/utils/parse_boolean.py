from typing import Optional
from rest_framework.exceptions import ValidationError


def parse_boolean(value: Optional[str], default=None) -> bool:
    if value is None or value == "":
        return default

    val = str(value).lower()
    if val in ("true", "1"):
        return True
    elif val in ("false", "0"):
        return False
    else:
        raise ValidationError(
            f"Invalid boolean value: {value}. Expected 'true', 'false', '1', or '0'."
        )
