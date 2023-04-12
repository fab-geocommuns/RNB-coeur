from django.contrib.auth.models import User


class RNBUser:
    def __init__(self, m: User):
        if not isinstance(m, User):
            raise TypeError(
                f"RNBUser must be initialised with a User instance. {type(m)} given."
            )

        self.m = m

    def get_managed_insee_codes(self) -> list:
        codes = []
        for org in self.m.organizations.all():
            codes += org.managed_cities

        return list(set(codes))
