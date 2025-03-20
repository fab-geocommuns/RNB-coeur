import base64
from django.contrib.auth.models import User


def get_b64_user_id(user: User) -> str:
    return base64.b64encode(user.id)
