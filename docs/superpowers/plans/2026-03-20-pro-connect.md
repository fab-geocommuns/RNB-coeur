# Pro Connect OIDC Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Pro Connect (OIDC) authentication endpoints to the RNB backend so the separate Next.js frontend can offer "Se connecter avec Pro Connect" alongside the existing email/password login.

**Architecture:** 4 new GET endpoints under `/api/alpha/auth/pro_connect/` handle the OIDC authorize/callback/logout flow. A single file `pro_connect.py` contains views + OIDC utilities. A `ProConnectIdentity` model links a User to their Pro Connect `sub`. State is managed statelessly via `django.core.signing`.

**Tech Stack:** Django 6.0.3, DRF 3.16.1, authlib (OIDC/JWT), django.core.signing (stateless state)

**Spec:** `docs/superpowers/specs/2026-03-20-pro-connect-design.md`

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `app/pyproject.toml` | Modify | Add `authlib` dependency |
| `app/app/settings.py` | Modify | Add Pro Connect settings (6 vars) |
| `app/batid/models/others.py` | Modify | Add `ProConnectIdentity` model |
| `app/batid/models/__init__.py` | No change | Already re-exports `others.py` via `from .others import *` |
| `app/api_alpha/endpoints/auth/pro_connect.py` | Create | 4 views + 5 OIDC utility functions + 1 provisioning function |
| `app/api_alpha/urls.py` | Modify | Register 4 new routes |
| `app/api_alpha/tests/auth/test_pro_connect.py` | Create | 11 tests |
| `.env.app.example` | Modify | Add Pro Connect env vars |
| 1 migration file | Create (via makemigrations) | `ProConnectIdentity` table |

---

## Task 1: Infrastructure setup

**Files:**
- Modify: `app/pyproject.toml`
- Modify: `app/app/settings.py` (after line 243, `MIN_BUILDING_AREA`)
- Modify: `app/batid/models/others.py` (after `UserProfile`, line 223)
- Modify: `.env.app.example`

- [ ] **Step 1: Add authlib dependency**

In `app/pyproject.toml`, add to `[tool.poetry.dependencies]`:

```
authlib = "~1.5"
```

- [ ] **Step 2: Install dependency**

Run: `docker exec web poetry install`
Expected: authlib installed successfully

- [ ] **Step 3: Add ProConnectIdentity model**

In `app/batid/models/others.py`, after the `UserProfile` class (after line 223):

```python
class ProConnectIdentity(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="pro_connect")
    sub = models.CharField(max_length=255, unique=True, db_index=True)
    last_id_token = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
```

No need to update `__init__.py` — it already uses `from .others import *`.

- [ ] **Step 4: Create migration**

Run: `docker exec web python manage.py makemigrations batid`
Expected: Migration file created for `ProConnectIdentity`

- [ ] **Step 5: Apply migration**

Run: `docker exec web python manage.py migrate`
Expected: Migration applied successfully

- [ ] **Step 6: Add Pro Connect settings**

In `app/app/settings.py`, after line 243 (`MIN_BUILDING_AREA = 5`):

```python
# Pro Connect (OIDC)
PRO_CONNECT_CLIENT_ID = os.environ.get("PRO_CONNECT_CLIENT_ID")
PRO_CONNECT_CLIENT_SECRET = os.environ.get("PRO_CONNECT_CLIENT_SECRET")
PRO_CONNECT_DISCOVERY_URL = os.environ.get(
    "PRO_CONNECT_DISCOVERY_URL",
    "https://fca.integ01.dev-agentconnect.fr/api/v2/.well-known/openid-configuration",
)
PRO_CONNECT_SCOPES = "openid email given_name usual_name"
PRO_CONNECT_REDIRECT_URI = os.environ.get("PRO_CONNECT_REDIRECT_URI")
PRO_CONNECT_POST_LOGOUT_REDIRECT_URI = os.environ.get(
    "PRO_CONNECT_POST_LOGOUT_REDIRECT_URI"
)
PRO_CONNECT_ALLOWED_REDIRECT_URIS = [
    u.strip()
    for u in os.environ.get("PRO_CONNECT_ALLOWED_REDIRECT_URIS", "").split(",")
    if u.strip()
]
```

- [ ] **Step 7: Add env vars to .env.app.example**

Append to `.env.app.example`:

```
# Pro Connect (OIDC)
PRO_CONNECT_CLIENT_ID=
PRO_CONNECT_CLIENT_SECRET=
PRO_CONNECT_DISCOVERY_URL=https://fca.integ01.dev-agentconnect.fr/api/v2/.well-known/openid-configuration
PRO_CONNECT_REDIRECT_URI=http://localhost:8000/api/alpha/auth/pro_connect/callback/
PRO_CONNECT_POST_LOGOUT_REDIRECT_URI=http://localhost:8000/api/alpha/auth/pro_connect/logout/callback/
PRO_CONNECT_ALLOWED_REDIRECT_URIS=http://localhost:3000
```

- [ ] **Step 8: Commit**

```bash
git add app/pyproject.toml app/app/settings.py app/batid/models/others.py .env.app.example app/batid/migrations/
git commit -m "add ProConnectIdentity model, authlib dependency, and Pro Connect settings"
```

---

## Task 2: Authorize endpoint

**Files:**
- Create: `app/api_alpha/endpoints/auth/pro_connect.py`
- Create: `app/api_alpha/tests/auth/test_pro_connect.py`
- Modify: `app/api_alpha/urls.py`

- [ ] **Step 1: Write the failing test for authorize**

Create `app/api_alpha/tests/auth/test_pro_connect.py`:

```python
from unittest import mock
from urllib.parse import parse_qs
from urllib.parse import urlparse

from django.core import signing
from django.test import override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from batid.models import ProConnectIdentity
from batid.tests.factories.users import ContributorUserFactory

FAKE_OIDC_CONFIG = {
    "authorization_endpoint": "https://proconnect.example/authorize",
    "token_endpoint": "https://proconnect.example/token",
    "userinfo_endpoint": "https://proconnect.example/userinfo",
    "end_session_endpoint": "https://proconnect.example/logout",
    "jwks_uri": "https://proconnect.example/jwks",
}


@override_settings(
    PRO_CONNECT_CLIENT_ID="test-client-id",
    PRO_CONNECT_REDIRECT_URI="http://localhost:8000/api/alpha/auth/pro_connect/callback/",
    PRO_CONNECT_SCOPES="openid email given_name usual_name",
    PRO_CONNECT_ALLOWED_REDIRECT_URIS=["http://localhost:3000"],
)
class AuthorizeTest(APITestCase):
    """GET /authorize/ returns an authorization URL with state containing nonce and redirect_uri."""

    @mock.patch(
        "api_alpha.endpoints.auth.pro_connect.get_oidc_config",
        return_value=FAKE_OIDC_CONFIG,
    )
    def test_authorize_returns_authorization_url(self, mock_config):
        response = self.client.get(
            "/api/alpha/auth/pro_connect/authorize/",
            {"redirect_uri": "http://localhost:3000"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("authorization_url", data)
        self.assertIn("proconnect.example/authorize", data["authorization_url"])
        self.assertIn("state=", data["authorization_url"])

        # Verify state is decodable and contains nonce + redirect_uri
        parsed = urlparse(data["authorization_url"])
        params = parse_qs(parsed.query)
        state = params["state"][0]
        payload = signing.loads(state, salt="pro_connect", max_age=300)
        self.assertIn("nonce", payload)
        self.assertIn("redirect_uri", payload)
        self.assertEqual(payload["redirect_uri"], "http://localhost:3000")

    @mock.patch(
        "api_alpha.endpoints.auth.pro_connect.get_oidc_config",
        return_value=FAKE_OIDC_CONFIG,
    )
    def test_authorize_rejects_invalid_redirect_uri(self, mock_config):
        """Authorize rejects redirect_uri not in allowlist → 400."""
        response = self.client.get(
            "/api/alpha/auth/pro_connect/authorize/",
            {"redirect_uri": "https://evil.com"},
        )
        self.assertEqual(response.status_code, 400)

    @mock.patch(
        "api_alpha.endpoints.auth.pro_connect.get_oidc_config",
        return_value=FAKE_OIDC_CONFIG,
    )
    def test_authorize_rejects_missing_redirect_uri(self, mock_config):
        """Authorize rejects missing redirect_uri → 400."""
        response = self.client.get("/api/alpha/auth/pro_connect/authorize/")
        self.assertEqual(response.status_code, 400)
```

- [ ] **Step 2: Create the pro_connect.py file with the authorize view and get_oidc_config stub**

Create `app/api_alpha/endpoints/auth/pro_connect.py`:

```python
import secrets
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.core import signing
from django.core.cache import cache
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView


# ---------------------------------------------------------------------------
# OIDC utility functions
# ---------------------------------------------------------------------------

def get_oidc_config():
    """Fetch and cache the OIDC discovery document (1h TTL)."""
    cached = cache.get("pro_connect_oidc_config")
    if cached:
        return cached
    resp = requests.get(settings.PRO_CONNECT_DISCOVERY_URL, timeout=10)
    resp.raise_for_status()
    config = resp.json()
    cache.set("pro_connect_oidc_config", config, 3600)
    return config


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

class AuthorizeView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        redirect_uri = request.query_params.get("redirect_uri")
        if not redirect_uri or redirect_uri not in settings.PRO_CONNECT_ALLOWED_REDIRECT_URIS:
            return Response(
                {"error": "invalid_redirect_uri"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        nonce = secrets.token_urlsafe(32)
        state = signing.dumps(
            {"nonce": nonce, "redirect_uri": redirect_uri},
            salt="pro_connect",
        )

        oidc_config = get_oidc_config()
        params = urlencode({
            "response_type": "code",
            "client_id": settings.PRO_CONNECT_CLIENT_ID,
            "redirect_uri": settings.PRO_CONNECT_REDIRECT_URI,
            "scope": settings.PRO_CONNECT_SCOPES,
            "state": state,
            "nonce": nonce,
        })
        authorization_url = f"{oidc_config['authorization_endpoint']}?{params}"

        return Response({"authorization_url": authorization_url})
```

- [ ] **Step 3: Register the authorize URL**

In `app/api_alpha/urls.py`, add the import:

```python
from api_alpha.endpoints.auth.pro_connect import AuthorizeView
```

And add the path in the Authentification section (after line 125):

```python
    path("auth/pro_connect/authorize/", AuthorizeView.as_view()),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker exec web python manage.py test api_alpha.tests.auth.test_pro_connect.AuthorizeTest -v 2`
Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/api_alpha/endpoints/auth/pro_connect.py app/api_alpha/tests/auth/test_pro_connect.py app/api_alpha/urls.py
git commit -m "feat: add Pro Connect authorize endpoint"
```

---

## Task 3: Callback endpoint — OIDC utilities + provisioning + view

**Files:**
- Modify: `app/api_alpha/endpoints/auth/pro_connect.py`
- Modify: `app/api_alpha/tests/auth/test_pro_connect.py`
- Modify: `app/api_alpha/urls.py`

- [ ] **Step 1: Write failing tests for callback**

Append to `app/api_alpha/tests/auth/test_pro_connect.py`:

```python
FAKE_JWKS = {
    "keys": [{"kty": "RSA", "kid": "test-key", "n": "fake", "e": "AQAB"}]
}

FAKE_USERINFO = {
    "sub": "pro-connect-sub-123",
    "email": "agent@gouv.fr",
    "given_name": "Marie",
    "usual_name": "Dupont",
}


def _make_state(redirect_uri="http://localhost:3000", nonce="test-nonce"):
    return signing.dumps(
        {"nonce": nonce, "redirect_uri": redirect_uri},
        salt="pro_connect",
    )


def _mock_token_exchange(mock_post, id_token="fake-id-token", access_token="fake-access-token"):
    """Configure mock for token endpoint POST."""
    mock_response = mock.Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "access_token": access_token,
        "id_token": id_token,
        "token_type": "Bearer",
    }
    mock_post.return_value = mock_response


@override_settings(
    PRO_CONNECT_CLIENT_ID="test-client-id",
    PRO_CONNECT_CLIENT_SECRET="test-client-secret",
    PRO_CONNECT_REDIRECT_URI="http://localhost:8000/api/alpha/auth/pro_connect/callback/",
    PRO_CONNECT_SCOPES="openid email given_name usual_name",
    PRO_CONNECT_ALLOWED_REDIRECT_URIS=["http://localhost:3000"],
    CONTRIBUTORS_GROUP_NAME="Contributors",
)
class CallbackTest(APITestCase):
    def _call_callback(self, code="auth-code", state=None):
        if state is None:
            state = _make_state()
        return self.client.get(
            "/api/alpha/auth/pro_connect/callback/",
            {"code": code, "state": state},
        )

    @mock.patch("api_alpha.endpoints.auth.pro_connect.fetch_userinfo", return_value=FAKE_USERINFO)
    @mock.patch("api_alpha.endpoints.auth.pro_connect.verify_id_token", return_value={"nonce": "test-nonce"})
    @mock.patch("api_alpha.endpoints.auth.pro_connect.exchange_code_for_tokens", return_value=("fake-access-token", "fake-id-token"))
    def test_callback_creates_new_user(self, mock_exchange, mock_verify, mock_userinfo):
        """Callback with unknown sub and email creates User + UserProfile + ProConnectIdentity + Token + Contributors group."""
        from django.contrib.auth.models import Group, User

        Group.objects.get_or_create(name="Contributors")

        response = self._call_callback()

        self.assertEqual(response.status_code, 302)
        self.assertIn("token=", response.url)
        self.assertIn("http://localhost:3000", response.url)

        user = User.objects.get(email="agent@gouv.fr")
        self.assertTrue(user.is_active)
        self.assertFalse(user.has_usable_password())
        self.assertEqual(user.first_name, "Marie")
        self.assertEqual(user.last_name, "Dupont")
        self.assertTrue(user.groups.filter(name="Contributors").exists())
        self.assertTrue(hasattr(user, "profile"))
        self.assertTrue(hasattr(user, "pro_connect"))
        self.assertEqual(user.pro_connect.sub, "pro-connect-sub-123")
        self.assertTrue(Token.objects.filter(user=user).exists())

    @mock.patch("api_alpha.endpoints.auth.pro_connect.fetch_userinfo", return_value=FAKE_USERINFO)
    @mock.patch("api_alpha.endpoints.auth.pro_connect.verify_id_token", return_value={"nonce": "test-nonce"})
    @mock.patch("api_alpha.endpoints.auth.pro_connect.exchange_code_for_tokens", return_value=("fake-access-token", "fake-id-token"))
    def test_callback_links_existing_user_by_email(self, mock_exchange, mock_verify, mock_userinfo):
        """Callback with unknown sub but known email links ProConnectIdentity to existing user."""
        from django.contrib.auth.models import Group, User

        Group.objects.get_or_create(name="Contributors")
        existing_user = User.objects.create_user(
            username="existing", email="agent@gouv.fr", password="testpass123"
        )

        response = self._call_callback()

        self.assertEqual(response.status_code, 302)
        existing_user.refresh_from_db()
        self.assertTrue(hasattr(existing_user, "pro_connect"))
        self.assertEqual(existing_user.pro_connect.sub, "pro-connect-sub-123")
        # User keeps their password
        self.assertTrue(existing_user.has_usable_password())

    @mock.patch("api_alpha.endpoints.auth.pro_connect.fetch_userinfo", return_value=FAKE_USERINFO)
    @mock.patch("api_alpha.endpoints.auth.pro_connect.verify_id_token", return_value={"nonce": "test-nonce"})
    @mock.patch("api_alpha.endpoints.auth.pro_connect.exchange_code_for_tokens", return_value=("fake-access-token", "fake-id-token"))
    def test_callback_returns_existing_pro_connect_user(self, mock_exchange, mock_verify, mock_userinfo):
        """Callback with known sub updates User fields and last_id_token."""
        from django.contrib.auth.models import Group, User

        Group.objects.get_or_create(name="Contributors")
        user = User.objects.create_user(
            username="existing", email="agent@gouv.fr", password="testpass123",
            first_name="Old", last_name="Name",
        )
        ProConnectIdentity.objects.create(user=user, sub="pro-connect-sub-123", last_id_token="old-token")

        response = self._call_callback()

        self.assertEqual(response.status_code, 302)
        user.refresh_from_db()
        self.assertEqual(user.first_name, "Marie")
        self.assertEqual(user.last_name, "Dupont")
        self.assertEqual(user.pro_connect.last_id_token, "fake-id-token")

    def test_callback_invalid_state(self):
        """Callback with tampered state redirects with error."""
        response = self._call_callback(state="tampered-state")

        self.assertEqual(response.status_code, 302)
        self.assertIn("error=", response.url)
```

- [ ] **Step 2: Add OIDC utility functions to pro_connect.py**

Add after `get_oidc_config()` in `app/api_alpha/endpoints/auth/pro_connect.py`:

```python
from authlib.jose import jwt as jose_jwt


def get_jwks():
    """Fetch and cache JWKS public keys (1h TTL)."""
    cached = cache.get("pro_connect_jwks")
    if cached:
        return cached
    oidc_config = get_oidc_config()
    resp = requests.get(oidc_config["jwks_uri"], timeout=10)
    resp.raise_for_status()
    jwks = resp.json()
    cache.set("pro_connect_jwks", jwks, 3600)
    return jwks


def exchange_code_for_tokens(code):
    """Exchange authorization code for access_token and id_token."""
    oidc_config = get_oidc_config()
    resp = requests.post(
        oidc_config["token_endpoint"],
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.PRO_CONNECT_REDIRECT_URI,
            "client_id": settings.PRO_CONNECT_CLIENT_ID,
            "client_secret": settings.PRO_CONNECT_CLIENT_SECRET,
        },
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["access_token"], data["id_token"]


def verify_id_token(id_token, nonce):
    """Verify id_token JWT signature via JWKS and check nonce."""
    jwks = get_jwks()
    claims = jose_jwt.decode(id_token, jwks)
    claims.validate()
    if claims.get("nonce") != nonce:
        raise ValueError("Invalid nonce in id_token")
    return claims


def fetch_userinfo(access_token):
    """Fetch user claims from the userinfo endpoint."""
    oidc_config = get_oidc_config()
    resp = requests.get(
        oidc_config["userinfo_endpoint"],
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()
```

- [ ] **Step 3: Add provisioning function**

Add after the utility functions in `app/api_alpha/endpoints/auth/pro_connect.py`:

```python
from django.contrib.auth.models import Group
from django.contrib.auth.models import User
from django.db import transaction
from nanoid import generate as nanoid
from rest_framework.authtoken.models import Token

from batid.models import ProConnectIdentity
from batid.models import UserProfile


def get_or_create_user_from_pro_connect(userinfo, id_token):
    """Find or create a user from Pro Connect userinfo claims.

    Lookup order: by sub, then by email, then create new.
    Returns (user, token).
    """
    sub = userinfo["sub"]
    email = userinfo["email"]
    first_name = userinfo.get("given_name", "")
    last_name = userinfo.get("usual_name", "")

    # Step 1: Known Pro Connect identity
    try:
        identity = ProConnectIdentity.objects.select_related("user").get(sub=sub)
        user = identity.user
        user.email = email
        user.first_name = first_name
        user.last_name = last_name
        user.save(update_fields=["email", "first_name", "last_name"])
        identity.last_id_token = id_token
        identity.save(update_fields=["last_id_token", "updated_at"])
        token, _ = Token.objects.get_or_create(user=user)
        return user, token
    except ProConnectIdentity.DoesNotExist:
        pass

    # Step 2: Known email — link Pro Connect identity
    try:
        user = User.objects.get(email=email)
        if hasattr(user, "pro_connect"):
            raise ValueError(
                f"User {email} already has a Pro Connect identity with a different sub"
            )
        ProConnectIdentity.objects.create(user=user, sub=sub, last_id_token=id_token)
        user.first_name = first_name
        user.last_name = last_name
        user.save(update_fields=["first_name", "last_name"])
        token, _ = Token.objects.get_or_create(user=user)
        return user, token
    except User.DoesNotExist:
        pass

    # Step 3: Create new user
    with transaction.atomic():
        username = email.split("@")[0]
        if User.objects.filter(username=username).exists():
            username = f"{username}_{nanoid(size=6)}"

        user = User.objects.create(
            username=username,
            email=email,
            first_name=first_name,
            last_name=last_name,
            is_active=True,
        )
        user.set_unusable_password()
        user.save(update_fields=["password"])

        group, _ = Group.objects.get_or_create(
            name=settings.CONTRIBUTORS_GROUP_NAME
        )
        user.groups.add(group)

        UserProfile.objects.create(user=user)
        ProConnectIdentity.objects.create(user=user, sub=sub, last_id_token=id_token)
        token = Token.objects.create(user=user)

    return user, token
```

- [ ] **Step 4: Add CallbackView**

Add to the views section of `app/api_alpha/endpoints/auth/pro_connect.py`:

```python
from django.http import HttpResponseRedirect


class CallbackView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        code = request.query_params.get("code")
        state_str = request.query_params.get("state")

        if not code or not state_str:
            return HttpResponseRedirect("/?error=missing_parameters")

        # Decode and verify state
        try:
            state = signing.loads(state_str, salt="pro_connect", max_age=300)
        except signing.BadSignature:
            return HttpResponseRedirect("/?error=invalid_state")

        redirect_uri = state["redirect_uri"]
        nonce = state["nonce"]

        try:
            access_token, id_token = exchange_code_for_tokens(code)
            verify_id_token(id_token, nonce)
            userinfo = fetch_userinfo(access_token)
            user, token = get_or_create_user_from_pro_connect(userinfo, id_token)
        except Exception as e:
            error_params = urlencode({
                "error": "authentication_failed",
                "error_description": str(e),
            })
            return HttpResponseRedirect(f"{redirect_uri}?{error_params}")

        params = urlencode({
            "token": token.key,
            "user_id": user.id,
            "username": user.username,
        })
        return HttpResponseRedirect(f"{redirect_uri}?{params}")
```

- [ ] **Step 5: Register the callback URL**

In `app/api_alpha/urls.py`, update the import:

```python
from api_alpha.endpoints.auth.pro_connect import AuthorizeView
from api_alpha.endpoints.auth.pro_connect import CallbackView
```

Add the path:

```python
    path("auth/pro_connect/callback/", CallbackView.as_view()),
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `docker exec web python manage.py test api_alpha.tests.auth.test_pro_connect -v 2`
Expected: 7 tests PASS (3 authorize + 4 callback)

- [ ] **Step 7: Commit**

```bash
git add app/api_alpha/endpoints/auth/pro_connect.py app/api_alpha/tests/auth/test_pro_connect.py app/api_alpha/urls.py
git commit -m "feat: add Pro Connect callback endpoint with OIDC utilities and user provisioning"
```

---

## Task 4: Logout endpoint

**Files:**
- Modify: `app/api_alpha/endpoints/auth/pro_connect.py`
- Modify: `app/api_alpha/tests/auth/test_pro_connect.py`
- Modify: `app/api_alpha/urls.py`

- [ ] **Step 1: Write failing tests for logout**

Append to `app/api_alpha/tests/auth/test_pro_connect.py`:

```python
@override_settings(
    PRO_CONNECT_POST_LOGOUT_REDIRECT_URI="http://localhost:8000/api/alpha/auth/pro_connect/logout/callback/",
    PRO_CONNECT_ALLOWED_REDIRECT_URIS=["http://localhost:3000"],
)
class LogoutTest(APITestCase):
    @mock.patch(
        "api_alpha.endpoints.auth.pro_connect.get_oidc_config",
        return_value=FAKE_OIDC_CONFIG,
    )
    def test_logout_redirects_to_pro_connect(self, mock_config):
        """Authenticated user with ProConnectIdentity → redirect 302 to Pro Connect end_session_endpoint."""
        user = ContributorUserFactory(is_active=True)
        ProConnectIdentity.objects.create(
            user=user, sub="sub-123", last_id_token="the-id-token"
        )
        token = Token.objects.get(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        response = self.client.get(
            "/api/alpha/auth/pro_connect/logout/",
            {"post_logout_redirect_uri": "http://localhost:3000"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("proconnect.example/logout", response.url)
        self.assertIn("id_token_hint=the-id-token", response.url)
        self.assertIn("state=", response.url)

    def test_logout_without_pro_connect_identity(self):
        """Authenticated user without ProConnectIdentity → 400."""
        user = ContributorUserFactory(is_active=True)
        token = Token.objects.get(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        response = self.client.get(
            "/api/alpha/auth/pro_connect/logout/",
            {"post_logout_redirect_uri": "http://localhost:3000"},
        )

        self.assertEqual(response.status_code, 400)
```

- [ ] **Step 2: Add LogoutView**

Add to `app/api_alpha/endpoints/auth/pro_connect.py`:

```python
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import TokenAuthentication


class LogoutView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            identity = request.user.pro_connect
        except ProConnectIdentity.DoesNotExist:
            return Response(
                {"error": "no_pro_connect_identity"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        post_logout_redirect_uri = request.query_params.get(
            "post_logout_redirect_uri", ""
        )
        if post_logout_redirect_uri and post_logout_redirect_uri not in settings.PRO_CONNECT_ALLOWED_REDIRECT_URIS:
            return Response(
                {"error": "invalid_redirect_uri"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        state = signing.dumps(
            {"post_logout_redirect_uri": post_logout_redirect_uri},
            salt="pro_connect_logout",
        )

        oidc_config = get_oidc_config()
        params = urlencode({
            "id_token_hint": identity.last_id_token,
            "state": state,
            "post_logout_redirect_uri": settings.PRO_CONNECT_POST_LOGOUT_REDIRECT_URI,
        })
        return HttpResponseRedirect(
            f"{oidc_config['end_session_endpoint']}?{params}"
        )
```

- [ ] **Step 3: Register the logout URL**

In `app/api_alpha/urls.py`, update the import:

```python
from api_alpha.endpoints.auth.pro_connect import AuthorizeView
from api_alpha.endpoints.auth.pro_connect import CallbackView
from api_alpha.endpoints.auth.pro_connect import LogoutView
```

Add the path:

```python
    path("auth/pro_connect/logout/", LogoutView.as_view()),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker exec web python manage.py test api_alpha.tests.auth.test_pro_connect.LogoutTest -v 2`
Expected: 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/api_alpha/endpoints/auth/pro_connect.py app/api_alpha/tests/auth/test_pro_connect.py app/api_alpha/urls.py
git commit -m "feat: add Pro Connect logout endpoint"
```

---

## Task 5: Logout callback endpoint

**Files:**
- Modify: `app/api_alpha/endpoints/auth/pro_connect.py`
- Modify: `app/api_alpha/tests/auth/test_pro_connect.py`
- Modify: `app/api_alpha/urls.py`

- [ ] **Step 1: Write failing test for logout callback**

Append to `app/api_alpha/tests/auth/test_pro_connect.py`:

```python
class LogoutCallbackTest(APITestCase):
    def test_logout_callback_redirects_to_frontend(self):
        """Logout callback with valid state → redirect 302 to frontend post_logout_redirect_uri."""
        state = signing.dumps(
            {"post_logout_redirect_uri": "http://localhost:3000"},
            salt="pro_connect_logout",
        )

        response = self.client.get(
            "/api/alpha/auth/pro_connect/logout/callback/",
            {"state": state},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "http://localhost:3000")

    def test_logout_callback_invalid_state(self):
        """Logout callback with tampered state → 400."""
        response = self.client.get(
            "/api/alpha/auth/pro_connect/logout/callback/",
            {"state": "tampered"},
        )

        self.assertEqual(response.status_code, 400)
```

- [ ] **Step 2: Add LogoutCallbackView**

Add to `app/api_alpha/endpoints/auth/pro_connect.py`:

```python
class LogoutCallbackView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        state_str = request.query_params.get("state")
        try:
            state = signing.loads(state_str, salt="pro_connect_logout", max_age=300)
        except signing.BadSignature:
            return Response(
                {"error": "invalid_state"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return HttpResponseRedirect(state["post_logout_redirect_uri"])
```

- [ ] **Step 3: Register the logout callback URL**

In `app/api_alpha/urls.py`, update the import:

```python
from api_alpha.endpoints.auth.pro_connect import AuthorizeView
from api_alpha.endpoints.auth.pro_connect import CallbackView
from api_alpha.endpoints.auth.pro_connect import LogoutCallbackView
from api_alpha.endpoints.auth.pro_connect import LogoutView
```

Add the path:

```python
    path("auth/pro_connect/logout/callback/", LogoutCallbackView.as_view()),
```

- [ ] **Step 4: Run all tests to verify everything passes**

Run: `docker exec web python manage.py test api_alpha.tests.auth.test_pro_connect -v 2`
Expected: 11 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/api_alpha/endpoints/auth/pro_connect.py app/api_alpha/tests/auth/test_pro_connect.py app/api_alpha/urls.py
git commit -m "feat: add Pro Connect logout callback endpoint"
```

---

## Task 6: Final verification

- [ ] **Step 1: Run the full test suite**

Run: `docker exec web python manage.py test -v 2`
Expected: All existing tests still pass, plus 11 new Pro Connect tests

- [ ] **Step 2: Verify the final file structure**

Check that we have exactly:
- `app/api_alpha/endpoints/auth/pro_connect.py` (~190 lines)
- `app/api_alpha/tests/auth/test_pro_connect.py` (~190 lines)
- 1 new migration in `app/batid/migrations/`

- [ ] **Step 3: Final commit if any remaining changes**

```bash
git status
# If clean, nothing to do
```
