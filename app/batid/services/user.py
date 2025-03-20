import base64

from django.contrib.auth.models import User


def get_user_id_b64(user: User) -> str:
    return _int_to_b64(user.id)


def get_user_id_from_b64(user_id_b64: str) -> int:
    return _b64_to_int(user_id_b64)


def _int_to_b64(i: int) -> str:

    # Convert integer to string
    i_string = str(i)

    encoded_bytes = base64.b64encode(i_string.encode("utf-8"))
    # Convert bytes back to string
    return encoded_bytes.decode("utf-8")


def _b64_to_int(b64: str) -> int:
    decoded_bytes = base64.b64decode(b64)
    return int(decoded_bytes.decode("utf-8"))
