# Design : Intégration Pro Connect (OIDC) dans le backend RNB

## Contexte

Pro Connect est la solution d'identification de l'État français pour les agents publics, basée sur OpenID Connect / OAuth 2.0. L'objectif est de fournir les endpoints backend nécessaires pour que le site RNB (Next.js, repo séparé) puisse proposer l'authentification via Pro Connect en complément de l'authentification classique (email/mot de passe + token DRF).

## Décisions

| Élément | Décision | Justification |
|---|---|---|
| Bibliothèque OIDC | `authlib` | Contrôle fin du flow, adapté à une architecture headless (backend API + frontend séparé). `mozilla-django-oidc` est conçu pour des apps Django avec sessions. `social-auth-app-django` est overkill pour un seul provider. |
| Transmission du token au frontend | Dans l'URL de redirect (`?token=...`) | Simple, cohérent avec le niveau de sécurité existant. Le frontend nettoie l'URL immédiatement. |
| Modèle | Léger : `sub` + `last_id_token` uniquement | Les infos de profil (email, prénom, nom) mettent à jour le `User` Django. Extensible plus tard (ex: `siret`). |
| Organisation du code | Un seul fichier `pro_connect.py` | ~200 lignes, cohérent avec les patterns existants du projet. |
| Gestion du state | Stateless via `django.core.signing` | Pas de session ni de stockage serveur. Le nonce et le redirect_uri voyagent dans le state signé. |

## Modèle `ProConnectIdentity`

Dans `app/batid/models/others.py` :

```python
class ProConnectIdentity(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="pro_connect")
    sub = models.CharField(max_length=255, unique=True, db_index=True)
    last_id_token = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
```

- `sub` : identifiant unique et stable de l'utilisateur chez Pro Connect
- `last_id_token` : conservé pour le logout Pro Connect (`id_token_hint`)
- OneToOne avec `User` : un utilisateur ne peut avoir qu'une seule identité Pro Connect

## Settings

Dans `app/app/settings.py` :

```python
PRO_CONNECT_CLIENT_ID = os.environ.get("PRO_CONNECT_CLIENT_ID")
PRO_CONNECT_CLIENT_SECRET = os.environ.get("PRO_CONNECT_CLIENT_SECRET")
PRO_CONNECT_DISCOVERY_URL = os.environ.get(
    "PRO_CONNECT_DISCOVERY_URL",
    "https://fca.integ01.dev-agentconnect.fr/api/v2/.well-known/openid-configuration",
)
PRO_CONNECT_SCOPES = "openid email given_name usual_name"
PRO_CONNECT_REDIRECT_URI = os.environ.get("PRO_CONNECT_REDIRECT_URI")
PRO_CONNECT_POST_LOGOUT_REDIRECT_URI = os.environ.get("PRO_CONNECT_POST_LOGOUT_REDIRECT_URI")
PRO_CONNECT_ALLOWED_REDIRECT_URIS = os.environ.get("PRO_CONNECT_ALLOWED_REDIRECT_URIS", "").split(",")
```

- Discovery URL par défaut : environnement d'intégration Pro Connect
- Scopes réduits au minimum nécessaire
- Cache OIDC discovery / JWKS : cache Django par défaut (`LocMemCache`)

## Endpoints

Tous sous `/api/alpha/auth/pro_connect/`.

### `GET /authorize/`

Démarre le flow OIDC.

- Paramètre query : `redirect_uri` (URL du frontend où revenir après auth)
- **Valide `redirect_uri` contre `PRO_CONNECT_ALLOWED_REDIRECT_URIS`** — rejette avec 400 si non autorisé ou absent
- Génère un `nonce` via `secrets.token_urlsafe(32)`
- Encode `{nonce, redirect_uri}` dans un `state` signé via `django.core.signing.dumps(max_age=300)`
- Retourne JSON : `{"authorization_url": "https://..."}`
- Pas d'authentification requise

### `GET /callback/`

Reçoit le retour de Pro Connect après que l'utilisateur s'est identifié.

- Paramètres query : `code`, `state` (envoyés par Pro Connect)
- Flow :
  1. `signing.loads(state, max_age=300)` — récupère nonce + redirect_uri (rejette si falsifié/expiré)
  2. Échange `code` contre `{access_token, id_token}` via le token endpoint
  3. Vérifie la signature JWT de l'`id_token` (JWKS) et le `nonce`
  4. Appelle `/userinfo` immédiatement (access_token expire en 60s)
  5. Crée ou lie l'utilisateur (voir section Provisioning)
  6. Émet un token DRF
  7. Redirect 302 vers `{redirect_uri}?token={token}&user_id={id}&username={username}`
- En cas d'erreur : redirect vers `{redirect_uri}?error=...&error_description=...`
- Pas d'authentification requise

### `GET /logout/`

Initie le logout auprès de Pro Connect.

- Authentification requise (Token DRF)
- Paramètre query : `post_logout_redirect_uri` (URL frontend après déconnexion)
- Flow :
  1. Récupère `ProConnectIdentity` de l'utilisateur — 400 si absente
  2. Encode `post_logout_redirect_uri` dans un `state` signé (salt : `pro_connect_logout`, max_age=300)
  3. Redirect 302 vers `end_session_endpoint` de Pro Connect avec `id_token_hint` + `state` + `post_logout_redirect_uri` (du backend)
  Note : le token DRF n'est **pas** supprimé — le logout Pro Connect termine la session Pro Connect, pas l'accès API RNB

### `GET /logout/callback/`

Retour après logout Pro Connect.

- Paramètre query : `state`
- `signing.loads(state, salt='pro_connect_logout', max_age=300)` — récupère `post_logout_redirect_uri`
- Redirect 302 vers le frontend

## Provisioning / linking utilisateur

Fonction `get_or_create_user_from_pro_connect(userinfo, id_token)` :

**Étape 1 — Recherche par `sub`**

`ProConnectIdentity.objects.filter(sub=userinfo["sub"])` — si trouvé, met à jour le `User` (email, first_name, last_name) + `last_id_token`, retourne l'utilisateur.

**Étape 2 — Recherche par email**

`User.objects.filter(email=userinfo["email"])` — si trouvé et **n'a pas déjà** une `ProConnectIdentity` → crée une `ProConnectIdentity` liée à cet utilisateur existant. L'utilisateur conserve son mot de passe et peut se connecter des deux façons. Si l'utilisateur a déjà une `ProConnectIdentity` (liée à un autre `sub`), rejeter avec une erreur explicite.

**Étape 3 — Création d'un nouvel utilisateur**

Toute la création se fait dans un `transaction.atomic()` :

1. Génère un username depuis l'email (partie avant `@`, avec suffixe aléatoire si collision)
2. `User.objects.create(email=..., first_name=..., last_name=..., is_active=True)`
3. `user.set_unusable_password()`
4. Ajoute au groupe "Contributors"
5. Crée un `UserProfile`
6. Crée la `ProConnectIdentity`
7. Crée le token DRF

Note : **pas d'email de vérification** — contrairement au flow d'inscription classique, l'email est déjà vérifié par Pro Connect.

## Fonctions utilitaires OIDC

Dans le même fichier `pro_connect.py` :

- **`get_oidc_config()`** — fetch et cache (1h) le document de discovery
- **`get_jwks()`** — fetch et cache (1h) les clés publiques JWKS
- **`exchange_code_for_tokens(code)`** — POST vers le token endpoint via `authlib.integrations.requests_client.OAuth2Session`
- **`verify_id_token(id_token, nonce)`** — vérifie signature JWT via JWKS + nonce via `authlib.jose.jwt`
- **`fetch_userinfo(access_token)`** — GET vers le userinfo endpoint

## Sécurité

- **Redirect URI** : validé contre une allowlist (`PRO_CONNECT_ALLOWED_REDIRECT_URIS`) pour prévenir les open redirects
- **State** : signé avec `django.core.signing` (HMAC + SECRET_KEY), TTL 300s (login et logout)
- **Nonce** : `secrets.token_urlsafe(32)`, embarqué dans le state signé, vérifié dans l'id_token
- **JWT** : signature vérifiée via JWKS du provider
- **Mot de passe** : `set_unusable_password()` pour les comptes créés via Pro Connect
- **Token dans l'URL** : redirect one-shot, le frontend nettoie l'URL immédiatement
- **Provisioning** : `transaction.atomic()` pour éviter les états partiels

## Tests

Dans `app/api_alpha/tests/test_pro_connect.py`. Tous les appels HTTP vers Pro Connect sont mockés.

1. **test_authorize_returns_authorization_url** — réponse JSON valide, state décodable
2. **test_callback_creates_new_user** — création User + UserProfile + ProConnectIdentity + Token + groupe Contributors
3. **test_callback_links_existing_user_by_email** — liaison à un utilisateur existant (pas de doublon)
4. **test_callback_returns_existing_pro_connect_user** — mise à jour des champs User et last_id_token
5. **test_callback_invalid_state** — state falsifié → redirect avec error
6. **test_logout_redirects_to_pro_connect** — redirect 302 vers end_session_endpoint
7. **test_logout_without_pro_connect_identity** — utilisateur sans Pro Connect → 400

## Fichiers impactés

**Modifiés :**
- `app/pyproject.toml` — ajout `authlib`
- `app/app/settings.py` — config Pro Connect
- `app/batid/models/others.py` — modèle `ProConnectIdentity`
- `app/api_alpha/urls.py` — 4 nouvelles routes
- `.env.app.example` — variables d'environnement

**Créés :**
- `app/api_alpha/endpoints/auth/pro_connect.py` — vues + utilitaires OIDC
- `app/api_alpha/tests/test_pro_connect.py` — tests
- 1 migration
