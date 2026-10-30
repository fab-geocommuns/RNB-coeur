import hashlib

from rest_framework.throttling import ScopedRateThrottle


class LoginRateThrottle(ScopedRateThrottle):
    """Count password attempts per submitted identifier, not per IP.

    RNB-site calls /login/ from its server: keyed by IP, every site login would share
    one counter. Falls back to the client IP when no identifier is submitted.
    """

    def get_cache_key(self, request, view):
        data = request.data if isinstance(request.data, dict) else {}
        identifier = str(data.get("username", "")).strip().lower()
        if identifier:
            ident = hashlib.sha256(identifier.encode()).hexdigest()
        else:
            ident = self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}
