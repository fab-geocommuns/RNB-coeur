import hashlib

from django.contrib.auth.models import User
from django.db.models import Q
from rest_framework.throttling import ScopedRateThrottle


class LoginRateThrottle(ScopedRateThrottle):
    """Count password attempts per account, not per IP.

    RNB-site calls /login/ from its server: keyed by IP, every site login would share
    one counter. Falls back to the client IP when no identifier is submitted.
    """

    def get_cache_key(self, request, view):
        data = request.data if isinstance(request.data, dict) else {}
        identifier = str(data.get("username", "")).strip()
        if identifier:
            ident = self.account_key(identifier)
        else:
            ident = self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}

    @staticmethod
    def account_key(identifier: str) -> str:
        """The account's id when the identifier names exactly one account, so that its
        username and its email share a counter. Otherwise the hashed identifier."""
        # Same exact lookup as UsernameOrEmailBackend: every identifier that can log
        # an account in gets its counter. A case variant matches no account, cannot
        # log in, and its own counter grants nothing.
        account_ids = list(
            User.objects.filter(
                Q(username=identifier) | Q(email=identifier)
            ).values_list("id", flat=True)[:2]
        )
        if len(account_ids) == 1:
            return f"user-{account_ids[0]}"
        return hashlib.sha256(identifier.lower().encode()).hexdigest()
