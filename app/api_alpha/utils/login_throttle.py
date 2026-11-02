import hashlib

from django.contrib.auth.models import User
from django.db.models import Q
from rest_framework.throttling import ScopedRateThrottle


class LoginRateThrottle(ScopedRateThrottle):
    """Count password attempts per account, not per IP.

    RNB-site calls /login/ from its server: keyed by IP, every site login would share
    one counter. Falls back to the client IP when no identifier is submitted.
    """

    def allow_request(self, request, view):
        """Count with an atomic increment over a fixed window.

        ScopedRateThrottle reads the attempt history from the cache, then writes it
        back: concurrent attempts read the same history and all get through.
        """
        self.scope = getattr(view, self.scope_attr, None)
        if not self.scope:
            return True
        self.rate = self.get_rate()
        self.num_requests, self.duration = self.parse_rate(self.rate)
        self.now = self.timer()
        window = int(self.now // self.duration)
        key = f"{self.get_cache_key(request, view)}_{window}"
        # The key outlives its window, so incr never meets an expired key.
        self.cache.add(key, 0, 2 * self.duration)
        return self.cache.incr(key) <= self.num_requests

    def wait(self):
        """Seconds until the current window ends."""
        return self.duration - self.now % self.duration

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
