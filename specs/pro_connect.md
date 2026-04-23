# Plan : Intégration Pro Connect (OIDC) dans le backend RNB

## Contexte

Pro Connect est la solution d'identification de l'État français pour les agents publics, basée sur OpenID Connect / OAuth 2.0. L'objectif est de fournir les endpoints backend nécessaires pour que le site RNB (repo séparé, Next.js + NextAuth) puisse proposer l'authentification via Pro Connect. Actuellement, le backend utilise uniquement une authentification par username/email + mot de passe avec des tokens DRF.

## Choix de la bibliothèque : `authlib`

- `authlib` offre un contrôle fin sur chaque étape du flux OIDC (discovery, authorization, token exchange, JWT verification)
- Activement maintenu, supporte OIDC discovery nativement
- Critique : l'access_token Pro Connect n'est valide que 60 secondes, il faut appeler userinfo immédiatement

## Fichiers à modifier

| Fichier                      | Action                                   |
| ---------------------------- | ---------------------------------------- |
| `app/pyproject.toml`         | Ajouter `authlib`                        |
| `app/app/settings.py`        | Ajouter config Pro Connect               |
| `app/batid/models/others.py` | Ajouter modèle `ProConnectIdentity`      |
| `app/api_alpha/urls.py`      | Enregistrer 4 nouveaux endpoints         |
| `.env.app.example`           | Ajouter variables Pro Connect            |

## Fichiers à créer

| Fichier                                                | Contenu                                               |
| ------------------------------------------------------ | ----------------------------------------------------- |
| `app/api_alpha/endpoints/auth/pro_connect/__init__.py` | Module init                                           |
| `app/api_alpha/endpoints/auth/pro_connect/views.py`    | 4 vues (authorize, callback, logout, logout callback) |
| `app/api_alpha/endpoints/auth/pro_connect/services.py` | Client OIDC, provisioning utilisateur                 |
| `app/api_alpha/tests/auth/test_pro_connect.py`         | Tests                                                 |

## 1. Modèle `ProConnectIdentity`

Dans `app/batid/models/others.py`, après `UserProfile` :

```python
class ProConnectIdentity(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="pro_connect")
    sub = models.CharField(max_length=255, unique=True, db_index=True)
    email = models.CharField(max_length=255)
    given_name = models.CharField(max_length=255, blank=True)
    usual_name = models.CharField(max_length=255, blank=True)
    uid = models.CharField(max_length=255, blank=True)
    siret = models.CharField(max_length=14, blank=True)
    idp_id = models.CharField(max_length=255, blank=True)
    last_id_token = models.TextField(blank=True)  # pour le logout
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
```

Migration à créer via `makemigrations`.

## 2. Settings (`app/app/settings.py`)

```python
# Pro Connect (OIDC)
PRO_CONNECT_CLIENT_ID = os.environ.get("PRO_CONNECT_CLIENT_ID")
PRO_CONNECT_CLIENT_SECRET = os.environ.get("PRO_CONNECT_CLIENT_SECRET")
PRO_CONNECT_DISCOVERY_URL = os.environ.get(
    "PRO_CONNECT_DISCOVERY_URL",
    "https://fca.integ01.dev-agentconnect.fr/api/v2/.well-known/openid-configuration",
)
PRO_CONNECT_SCOPES = "openid email given_name usual_name uid siret idp_id phone"
PRO_CONNECT_REDIRECT_URI = os.environ.get("PRO_CONNECT_REDIRECT_URI")  # callback backend
PRO_CONNECT_POST_LOGOUT_REDIRECT_URI = os.environ.get("PRO_CONNECT_POST_LOGOUT_REDIRECT_URI")
```

Pas de configuration de cache supplémentaire : le cache par défaut (`LocMemCache`) est suffisant pour mettre en cache le document OIDC discovery et les clés JWKS.

## 3. Endpoints

Tous sous `/api/alpha/auth/pro_connect/` :

### 3a. `GET /auth/pro_connect/authorize/`

- Paramètre query optionnel : `redirect_uri` (URL frontend où rediriger après callback)
- Génère un `nonce` (via `secrets.token_urlsafe(32)`)
- Encode `nonce` + `frontend_redirect_uri` dans le `state` via `django.core.signing.dumps(..., salt='pro_connect', max_age=300)` — pas de stockage serveur
- Retourne JSON : `{"authorization_url": "https://...", "state": "..."}`
- Pas d'authentification requise

### 3b. `GET /auth/pro_connect/callback/`

- Paramètres query reçus de Pro Connect : `code`, `state`
- Flow :
  1. Décoder et vérifier le `state` via `signing.loads(state, salt='pro_connect', max_age=300)` — lève une exception si expiré ou falsifié
  2. Échanger `code` contre tokens via le token endpoint Pro Connect
  3. Vérifier la signature JWT de l'`id_token` (JWKS) et le `nonce`
  4. Appeler immédiatement userinfo avec l'access_token
  5. Provisioning/linking utilisateur (voir section 4)
  6. Émettre un token DRF (`Token.objects.get_or_create(user=user)`)
  7. Redirect 302 vers `{frontend_redirect_uri}?token={token_key}&user_id={user.id}&username={user.username}`
- En cas d'erreur : redirect vers `{frontend_redirect_uri}?error=...&error_description=...`
- Pas d'authentification requise

### 3c. `GET /auth/pro_connect/logout/`

- Authentification requise (Token DRF)
- Paramètre query optionnel : `post_logout_redirect_uri`
- Flow :
  1. Récupérer `ProConnectIdentity` de l'utilisateur et le `last_id_token`
  2. Si pas d'identité Pro Connect → 400
  3. Encoder `post_logout_redirect_uri` dans un `state` signé via `signing.dumps(..., salt='pro_connect_logout')`
  4. Supprimer le token DRF
  5. Redirect 302 vers `end_session_endpoint` avec `id_token_hint`, `state`, `post_logout_redirect_uri` (du backend)

### 3d. `GET /auth/pro_connect/logout/callback/`

- Paramètre query : `state`
- Décoder et vérifier le `state` via `signing.loads(state, salt='pro_connect_logout')`
- Redirect 302 vers le `post_logout_redirect_uri` du frontend

## 4. Logique de provisioning/linking (`services.py`)

Fonction `get_or_create_user_from_pro_connect(userinfo)` :

1. **Recherche par `sub`** : `ProConnectIdentity.objects.filter(sub=userinfo["sub"])` → si trouvé, mettre à jour les claims, retourner `identity.user`
2. **Recherche par email** : `User.objects.filter(email=userinfo["email"])` → si trouvé, créer `ProConnectIdentity` lié à cet utilisateur existant
3. **Création** :
   - Générer un username depuis l'email (partie avant `@` + suffixe nanoid si collision)
   - `User.objects.create(first_name, last_name, email, is_active=True)`
   - `user.set_unusable_password()` (pas de login par mot de passe)
   - Ajouter au groupe "Contributors" (réutiliser le pattern de `UserSerializer.create()` dans `serializers.py:703`)
   - Créer `UserProfile`
   - Créer `Token` DRF
   - Créer `ProConnectIdentity`

Le `last_id_token` est mis à jour à chaque authentification pour être disponible au logout.

## 5. Client OIDC (`services.py`)

```python
def get_oidc_config():
    """Fetch et cache le document de discovery OIDC (TTL 1h) via LocMemCache."""

def get_jwks():
    """Fetch et cache les clés JWKS pour vérification des id_tokens (TTL 1h) via LocMemCache."""

def create_oauth_session():
    """Crée une session OAuth2 authlib configurée pour Pro Connect."""
```

Utiliser `authlib.integrations.requests_client.OAuth2Session` pour le token exchange et `authlib.jose.jwt` pour la vérification JWT.

## 6. Dépendance

Ajouter dans `app/pyproject.toml` :

```
authlib = "~1.5"
```

## 7. Variables d'environnement

Ajouter dans `.env.app.example` :

```
PRO_CONNECT_CLIENT_ID=
PRO_CONNECT_CLIENT_SECRET=
PRO_CONNECT_DISCOVERY_URL=https://fca.integ01.dev-agentconnect.fr/api/v2/.well-known/openid-configuration
PRO_CONNECT_REDIRECT_URI=http://localhost:8000/api/alpha/auth/pro_connect/callback/
PRO_CONNECT_POST_LOGOUT_REDIRECT_URI=http://localhost:3000
```

## 8. Tests (`test_pro_connect.py`)

Mocker les appels HTTP vers Pro Connect (token exchange, userinfo, OIDC discovery, JWKS) :

1. **test_authorize_returns_authorization_url** : vérifie la réponse JSON et que le `state` est décodable via `signing.loads`
2. **test_callback_creates_new_user** : mock token exchange + userinfo, vérifie création User + UserProfile + ProConnectIdentity + Token + ajout au groupe Contributors
3. **test_callback_links_existing_user_by_email** : créer un utilisateur existant, vérifier qu'il est lié (pas de doublon)
4. **test_callback_returns_existing_pro_connect_user** : utilisateur avec ProConnectIdentity existant, vérifier la mise à jour des claims
5. **test_callback_invalid_state** : state falsifié/expiré → redirect avec error
6. **test_logout_redirects_to_pro_connect** : utilisateur Pro Connect → redirect vers end_session
7. **test_logout_without_pro_connect_identity** : utilisateur classique → 400

## 9. Ordre d'implémentation

1. Ajouter `authlib` dans `pyproject.toml`
2. Ajouter le modèle `ProConnectIdentity` + migration
3. Ajouter les settings Pro Connect
4. Ajouter les variables d'env dans `.env.app.example`
5. Créer `services.py` (client OIDC, provisioning)
6. Créer `views.py` (4 vues)
7. Enregistrer les URLs dans `urls.py`
8. Créer les tests
9. Lancer les tests

## 10. Sécurité

- **State** : signé avec `django.core.signing` (HMAC + SECRET_KEY), TTL 300s, falsification détectée automatiquement
- **Nonce** : `secrets.token_urlsafe(32)`, embarqué dans le `state` signé, vérifié dans le claim du `id_token`
- **JWT** : signature vérifiée via JWKS du provider
- **Mot de passe** : `set_unusable_password()` pour les comptes créés via Pro Connect
- **Token dans l'URL de redirect** : acceptable car redirect one-shot vers le frontend. Le frontend doit extraire le token et nettoyer l'URL

## 11. Vérification

1. `docker exec web python manage.py test api_alpha.tests.auth.test_pro_connect`
2. Vérifier manuellement en configurant les credentials Pro Connect de test (integ01) et en testant le flow complet depuis le frontend
