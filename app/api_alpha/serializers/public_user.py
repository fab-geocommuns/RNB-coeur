from django.contrib.auth.models import User


class PublicUserSerializer:
    def __init__(self, user: User | None):
        self.user = user

    def to_representation(self) -> dict:
        return {
            "display_name": self.display_name(),
            "id": self.user.pk if self.user is not None else None,
            "username": self.user.username if self.user is not None else None,
        }

    def display_name(self) -> str:
        if self.user is None:
            return "Anonyme"

        if not self.user.first_name and not self.user.last_name:
            return self.user.username

        if self.user.last_name is None or len(self.user.last_name) == 0:
            return self.user.first_name

        return f"{self.user.first_name} {self.user.last_name[0]}."
