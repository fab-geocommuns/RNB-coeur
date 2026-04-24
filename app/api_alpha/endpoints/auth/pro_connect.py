import logging
import secrets
from urllib.parse import urlencode
from urllib.parse import urlparse

from batid.services.url import add_params_to_url

import requests
from authlib.jose import jwt as jose_jwt
from django.conf import settings
from django.contrib.auth.models import Group
from django.contrib.auth.models import User
from django.core import signing
from django.core.cache import cache
from django.db import transaction
from django.http import HttpResponseRedirect
from django.utils import timezone
from rest_framework import status
from rest_framework.authentication import TokenAuthentication
from rest_framework.authtoken.models import Token
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from batid.models import ProConnectIdentity
from batid.models import UserProfile

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pro Connect — OAuth 2.0 + OpenID Connect (OIDC) flow overview
# ---------------------------------------------------------------------------
#
# Pro Connect is a French government identity provider (IdP) based on OIDC,
# which is an identity layer on top of OAuth 2.0.
#
# LOGIN / SIGNUP FLOW (Authorization Code Flow)
# ──────────────────────────────────────────────
#  1. Website (rnb-site)
#  - user clicks "Login with Pro Connect".
#  - the site calls AuthorizeView to get the authorization URL.
#
#  2. AuthorizeView (rnb-coeur)
#  — generates a nonce + state, builds the Pro Connect, authorization URL, and returns it to the site.
#
#  3. Website redirects (rnb-site)
#  - the website receives the AuthorizeView response and uses the authorization URL it contains to redirect the user
#  to the Pro Connect site
#
#  4. Pro Connect (outside RNB)
#  — authenticates the user, then redirects the browser directly to PRO_CONNECT_REDIRECT_URI with ?code=...&state=...
#
#  5. CallbackView (rnb-coeur)
#  — verifies the state, exchanges the code for tokens, (access_token + id_token),
#  - verifies the id_token, fetches the userinfo JWT,
#  - creates/updates the Django user, then redirects the browser back to the site with the session token.
#
#  6. Website (rnb-site)
#  - user lands on the redirect_url the website provided in step 1.
#
# LOGOUT FLOW
# ───────────
#  1. Website (rnb-site)
#  - user clicks "Logout".
#  - the site calls LogoutView with the token and a post_logout_redirect_uri.
#
#  2. LogoutView (rnb-coeur)
#  - builds a signed state containing the post_logout_redirect_uri.
#  - redirects the browser to Pro Connect's end_session endpoint with the
#    id_token_hint + state, so Pro Connect can terminate its own session.
#
#  3. Pro Connect (outside RNB)
#  - logs the user out, then redirects the browser directly to
#    PRO_CONNECT_POST_LOGOUT_REDIRECT_URI with ?state=...
#
#  4. LogoutCallbackView (rnb-coeur)
#  - verifies the state, then redirects the browser to the post_logout_redirect_uri.
#
#  5. Website (rnb-site)
#  - user lands on the post_logout_redirect_uri provided in step 1.
#
# KEY CONCEPTS
# ────────────
#  OIDC (OpenID Connect)
#    A standard identity layer built on top of OAuth 2.0. OAuth 2.0 only handles
#    authorization ("can this app access this resource?"). OIDC adds authentication
#    ("who is this user?") by introducing the id_token and the userinfo endpoint.
#    Pro Connect is an OIDC provider. We are the OIDC client (also called "relying party").
#
#  nonce
#    A random value we generate and embed in the authorization request (step 2).
#    Pro Connect echoes it back inside the id_token. We check it matches (step 5).
#    Purpose: ensures the token was issued for *this specific request* and cannot
#    be reused by an attacker who intercepts an old token (replay attack prevention).
#
#  JWKS (JSON Web Key Set)
#    The set of Pro Connect's public keys, published at a well-known URL (jwks_uri).
#    We use them to verify that the id_token and userinfo JWT were really signed by
#    Pro Connect and have not been tampered with — without sharing any secret.
#    Keys are fetched once and cached for 1 hour (see get_jwks()).


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
    """Fetch user claims from the userinfo endpoint.

    Pro Connect returns a signed JWT, not plain JSON.
    """
    oidc_config = get_oidc_config()
    resp = requests.get(
        oidc_config["userinfo_endpoint"],
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    resp.raise_for_status()
    content_type = resp.headers.get("Content-Type", "")
    if "application/jwt" in content_type or "application/json" not in content_type:
        jwks = get_jwks()
        claims = jose_jwt.decode(resp.text, jwks)
        return dict(claims)
    return resp.json()


# ---------------------------------------------------------------------------
# User provisioning
# ---------------------------------------------------------------------------


def get_or_create_user_from_pro_connect(userinfo, id_token):
    """Find or create a user from Pro Connect userinfo claims.

    Lookup order: by sub, then by email, then create new.
    Returns (user, token).
    """
    sub = userinfo["sub"]
    email = userinfo["email"]
    first_name = userinfo.get("given_name", "")
    last_name = userinfo.get("usual_name", "")
    siret = userinfo.get("siret", "")

    # Step 1: Known Pro Connect identity
    try:
        identity = ProConnectIdentity.objects.select_related("user").get(sub=sub)
        user = identity.user
        user.email = email
        user.first_name = first_name
        user.last_name = last_name
        user.save(update_fields=["email", "first_name", "last_name"])
        identity.last_id_token = id_token
        identity.siret = siret
        identity.save(update_fields=["last_id_token", "siret", "updated_at"])
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
        ProConnectIdentity.objects.create(
            user=user, sub=sub, last_id_token=id_token, siret=siret
        )
        user.first_name = first_name
        user.last_name = last_name
        if not user.is_active:
            user.is_active = True
            user.set_unusable_password()
        user.save(update_fields=["first_name", "last_name", "is_active", "password"])
        token, _ = Token.objects.get_or_create(user=user)
        return user, token
    except User.DoesNotExist:
        pass

    # Step 3: Create new user
    with transaction.atomic():
        username = email.split("@")[0]
        if User.objects.filter(username=username).exists():
            index = 2
            while User.objects.filter(username=f"{username}_{index}").exists():
                index += 1
            username = f"{username}_{index}"

        user = User.objects.create(
            username=username,
            email=email,
            first_name=first_name,
            last_name=last_name,
            is_active=True,
        )
        user.set_unusable_password()
        user.save(update_fields=["password"])

        group, _ = Group.objects.get_or_create(name=settings.CONTRIBUTORS_GROUP_NAME)
        user.groups.add(group)

        UserProfile.objects.create(user=user)
        ProConnectIdentity.objects.create(
            user=user, sub=sub, last_id_token=id_token, siret=siret
        )
        token = Token.objects.create(user=user)

    return user, token


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------


class AuthorizeView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        redirect_uri = request.query_params.get("redirect_uri")
        # Strip query string and fragment before the allowlist check so that
        # embedded params like ?redirect=… are allowed when the base path is whitelisted.
        redirect_uri_base = (
            urlparse(redirect_uri)._replace(query="", fragment="").geturl()
            if redirect_uri
            else None
        )
        if (
            not redirect_uri
            or redirect_uri_base not in settings.PRO_CONNECT_ALLOWED_REDIRECT_URIS
        ):
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
        params = urlencode(
            {
                "response_type": "code",
                "client_id": settings.PRO_CONNECT_CLIENT_ID,
                "redirect_uri": settings.PRO_CONNECT_REDIRECT_URI,
                "scope": settings.PRO_CONNECT_SCOPES,
                "state": state,
                "nonce": nonce,
                "acr_values": "eidas1",
            }
        )
        authorization_url = f"{oidc_config['authorization_endpoint']}?{params}"

        return Response({"authorization_url": authorization_url})


class CallbackView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        code = request.query_params.get("code")
        state_str = request.query_params.get("state")

        fallback_uri = getattr(settings, "FRONTEND_URL", "/") or "/"

        if not code or not state_str:
            return HttpResponseRedirect(f"{fallback_uri}?error=missing_parameters")

        # Decode and verify state
        try:
            state = signing.loads(state_str, salt="pro_connect", max_age=300)
        except signing.BadSignature:
            return HttpResponseRedirect(f"{fallback_uri}?error=invalid_state")

        redirect_uri = state["redirect_uri"]
        nonce = state["nonce"]

        try:
            access_token, id_token = exchange_code_for_tokens(code)
            verify_id_token(id_token, nonce)
            userinfo = fetch_userinfo(access_token)
            user, token = get_or_create_user_from_pro_connect(userinfo, id_token)

            if not user.is_active:
                # We block any user we disabled manually
                return HttpResponseRedirect(
                    add_params_to_url(redirect_uri, {"error": "account_disabled"})
                )

            user.last_login = timezone.now()
            user.save(update_fields=["last_login"])

        except Exception:
            logger.exception("Pro Connect callback failed")
            return HttpResponseRedirect(
                add_params_to_url(
                    redirect_uri,
                    {
                        "error": "authentication_failed",
                        "error_description": "An error occurred during authentication",
                    },
                )
            )

        return HttpResponseRedirect(
            add_params_to_url(
                redirect_uri,
                {
                    "token": token.key,
                    "user_id": user.id,
                    "username": user.username,
                },
            )
        )


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
        if (
            post_logout_redirect_uri
            and post_logout_redirect_uri
            not in settings.PRO_CONNECT_ALLOWED_REDIRECT_URIS
        ):
            return Response(
                {"error": "invalid_redirect_uri"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        state = signing.dumps(
            {"post_logout_redirect_uri": post_logout_redirect_uri},
            salt="pro_connect_logout",
        )

        oidc_config = get_oidc_config()
        params = urlencode(
            {
                "id_token_hint": identity.last_id_token,
                "state": state,
                "post_logout_redirect_uri": settings.PRO_CONNECT_POST_LOGOUT_REDIRECT_URI,
            }
        )
        return HttpResponseRedirect(f"{oidc_config['end_session_endpoint']}?{params}")


class LogoutCallbackView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        state_str = request.query_params.get("state")
        try:
            state = signing.loads(state_str, salt="pro_connect_logout", max_age=300)
        except (signing.BadSignature, TypeError):
            return Response(
                {"error": "invalid_state"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return HttpResponseRedirect(state["post_logout_redirect_uri"])
