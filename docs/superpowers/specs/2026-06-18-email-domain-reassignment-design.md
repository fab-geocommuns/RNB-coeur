# Rattachement par domaine email : réattribution avec priorité SIREN

Date : 2026-06-18

## Contexte & problème

Les organisations sont gérées **à la main** par l'équipe RNB. Quand une orga évolue
(ajout/modification d'un `email_domain`), on veut que le lien `User → Organization` se
mette à jour automatiquement, y compris pour des utilisateurs **déjà rattachés** à une
autre orga (assignation manuelle obsolète, ancienne orga, orga sans justification SIREN).

Le comportement actuel traite le domaine email comme un **fallback** : il ne rattache
que les utilisateurs **sans** orga. Voir l'ancien spec
`2026-06-16-organization-dedup-merge-design.md` (lignes 79-80, 213). Ce spec **remplace**
cette politique.

Rappel : `Organization.save()` déclenche déjà `link_organization_to_users(self)` via un
signal — éditer une orga rejoue donc le linking automatiquement.

## Règle unifiée

- **Match SIREN** (le SIRET ProConnect de l'user donne un SIREN qui matche `org.siren`) →
  autoritaire : (ré)attribue **toujours**. *(inchangé)*
- **Match domaine email** → (ré)attribue l'utilisateur, **sauf s'il est « ancré SIREN »**.

### Définition « ancré SIREN »

Un utilisateur est ancré SIREN si **les deux** conditions sont vraies :
1. il a un `pro_connect` avec un SIRET ≥ 9 caractères, et
2. son orga **actuelle** porte exactement ce SIREN (`current_org.siren == siret[:9]`).

Un user ancré SIREN est correctement placé par le signal autoritaire : un match par
domaine email ne doit jamais le débaucher. Un user qui a un SIRET ProConnect mais dont
l'orga actuelle **ne** correspond **pas** à ce SIREN est considéré « mal rangé » et peut
être déplacé par l'email.

## Conséquences sur le code (`app/batid/services/organization.py`)

### `link_user_to_organization(user)`

La protection SIREN est **automatique** : la requête candidate est
`Q(email_domain=...) | Q(siren=...)`. Si l'user matche un SIREN, l'orga correspondante
est dans les candidats et l'emporte (branche « 2 candidats » ou « 1 candidat SIREN »). On
ne tombe dans la branche « email seul » que s'il n'y a **aucun** match SIREN → la
réattribution y est toujours sûre.

→ **On retire le garde-fou `user_already_linked`** ajouté précédemment. La branche
« 1 candidat » rattache l'utilisateur sans condition (enrichissement inchangé).

### `link_organization_to_users(org)`

L'étape « email domain » ne filtre **plus** sur `profile__organization__isnull=True`.
Elle parcourt tous les utilisateurs (non-staff/superuser) dont le domaine email matche, et
les rattache, **en sautant les utilisateurs ancrés SIREN** :

```python
if org.email_domain:
    candidates = simple_users_qs.filter(email__endswith=f"@{org.email_domain}")
    for user in candidates:
        if _is_siren_anchored(user):
            continue
        _set_user_org(user, org)
```

Avec un helper :

```python
def _is_siren_anchored(user) -> bool:
    """True si l'orga actuelle de l'user porte exactement le SIREN de son SIRET ProConnect."""
    if not (hasattr(user, "pro_connect") and len(user.pro_connect.siret) >= 9):
        return False
    current = getattr(getattr(user, "profile", None), "organization", None)
    return current is not None and current.siren == user.pro_connect.siret[:9]
```

L'étape SIREN de la fonction (autoritaire) reste inchangée et s'exécute **avant** l'étape
email.

## Conséquences sur les tests (`app/batid/tests/test_organization_service.py`)

### Tests à inverser (encodaient « email = fallback »)

- `LinkUserToOrganizationTest.test_email_domain_not_applied_when_user_already_has_org`
- `LinkOrganizationToUsersTest.test_email_domain_skips_user_with_existing_org`
- `LinkSymmetryTest.test_email_domain_no_override_is_symmetric`

Dans ces trois cas, l'user n'a **pas** de ProConnect (donc non ancré) : il doit
désormais être **réattribué** à l'orga du domaine. Les renommer/réécrire pour exprimer
« l'email réattribue un user non-ancré » de façon symétrique.

### Test à ajouter (nouvelle garantie)

- **Un user ancré SIREN n'est pas débauché par un match email**, symétriquement :
  user avec SIRET ProConnect dont l'orga actuelle porte ce SIREN ; une autre orga porte
  son domaine email → après `link_user_to_organization(user)` **et** après
  `link_organization_to_users(domain_org)`, l'user reste dans son orga SIREN.

## Hors périmètre (YAGNI)

- Pas de tentative de retrouver la « vraie » orga SIREN d'un user mal rangé depuis
  l'étape email d'une autre orga (l'étape SIREN de la bonne orga s'en charge à son save).
- Pas de gestion de deux orgas partageant le même `email_domain` (`email_domain` est
  unique ; la dedup admin couvre les doublons résiduels).
