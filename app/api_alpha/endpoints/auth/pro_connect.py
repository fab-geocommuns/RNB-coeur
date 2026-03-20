import secrets
from urllib.parse import urlencode

import requests
from authlib.jose import jwt as jose_jwt
from django.conf import settings
from django.contrib.auth.models import Group
from django.contrib.auth.models import User
from django.core import signing
from django.core.cache import cache
from django.db import transaction
from django.http import HttpResponseRedirect
from nanoid import generate as nanoid
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from rest_framework.views import APIView

from batid.models import ProConnectIdentity
from batid.models import UserProfile


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
    """Fetch user claims from the userinfo endpoint."""
    oidc_config = get_oidc_config()
    resp = requests.get(
        oidc_config["userinfo_endpoint"],
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    resp.raise_for_status()
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
