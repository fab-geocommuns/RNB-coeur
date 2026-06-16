# Déduplication des organisations : rattachement intelligent + fusion admin

Date : 2026-06-16

## Contexte & problème

Des organisations en doublon se créent. Exemple typique :

1. Un admin crée manuellement une organisation, lui assigne un `email_domain` ; des
   utilisateurs s'y rattachent automatiquement par leur domaine d'email.
2. Plus tard, un utilisateur de cette même organisation s'inscrit/se connecte via
   ProConnect. On extrait le SIREN de son SIRET, aucune orga ne porte ce SIREN, donc
   une **nouvelle** organisation est créée. On a alors deux orgas pour la même entité.

Modèles concernés (rappel) :

- `Organization` (`app/batid/models/others.py`) : `name`, `short_name`, `managed_cities`
  (ArrayField), `siren` (unique, nullable), `email_domain` (unique, nullable).
  `Organization.save()` appelle déjà `link_organization_to_users(self)`.
- `UserProfile` : `OneToOne(User)` + `ForeignKey(Organization, on_delete=SET_NULL)`.
  **C'est la seule référence vers `Organization`.**
- `ProConnectIdentity` : `OneToOne(User)` + `siret`.
- Linking : `app/batid/services/organization.py` —
  `link_user_to_organization(user)` et `link_organization_to_users(org)`.

## Objectifs

1. **Éviter la création de doublons** au moment du login/inscription ProConnect, en
   rattachant l'utilisateur à une organisation existante correspondante et en
   enrichissant ses champs vides.
2. **Fournir un outil de fusion** dans l'admin Django pour réconcilier les doublons
   déjà présents en base.

---

## Partie 1 — Rattachement & enrichissement au passage ProConnect

### Où

`link_user_to_organization(user)` dans `app/batid/services/organization.py`, branche
SIREN (celle qui s'exécute quand `user.pro_connect.siret` fait ≥ 9 caractères).

Cette fonction est appelée par le callback ProConnect (`CallbackView`,
`app/api_alpha/endpoints/auth/pro_connect.py`) aussi bien au login qu'à l'inscription :
le comportement est donc identique dans les deux cas.

### Logique

On calcule :
- `siren = user.pro_connect.siret[:9]` (toujours non vide dans cette branche).
- `domain = user.email.split("@")[1]` si l'email contient un `@`, sinon `None`.

On cherche les organisations **candidates** :
- `siren_org` = orga dont `siren == siren` (champ unique → au plus une).
- `domain_org` = orga dont `email_domain == domain` (champ unique → au plus une), si
  `domain` non `None`.

Si `siren_org` et `domain_org` désignent la même ligne (même `pk`), on ne compte qu'un
seul candidat.

Décision selon le nombre de candidats distincts :

| Candidats | Action |
|-----------|--------|
| **0** | Création de l'orga depuis l'INSEE (`_create_org_from_siren`, comportement actuel inchangé). |
| **1** | Rattachement de l'utilisateur à ce candidat. **Enrichissement** : si `org.siren` est vide → on met `siren` ; si `org.email_domain` est vide → on met `domain`. Le `name` n'est **jamais** modifié. Si au moins un champ change, `org.save()` (ce qui re-déclenche `link_organization_to_users` et rattache les autres utilisateurs concernés). |
| **≥ 2** | On privilégie l'orga ayant le **même SIREN** (`siren_org`). Rattachement de l'utilisateur. **Pas d'enrichissement** (poser l'`email_domain` de l'autre orga violerait la contrainte d'unicité). La réconciliation des deux orgas se fera via l'outil de fusion admin. |

Dans tous les cas où une orga est obtenue, on appelle `_set_user_org(user, org)` puis on
`return` (comme aujourd'hui).

### Points d'attention

- « Vide » signifie `None` **ou** chaîne vide `""` (`not org.siren`), pour couvrir les
  deux façons dont Django peut stocker un `CharField(null=True, blank=True)`.
- Enrichir l'`email_domain` dans le cas « 1 candidat » est sûr : s'il n'y a qu'un
  candidat, c'est qu'aucune autre orga ne porte ce domaine (sinon il y aurait 2
  candidats). Idem pour l'enrichissement du `siren`.
- Le `name` saisi manuellement par l'admin est préservé (on n'écrase jamais le nom,
  même quand on ajoute le SIREN).
- La branche « email domain » existante (fallback en fin de fonction) reste inchangée :
  elle ne concerne que les utilisateurs **sans** `pro_connect`.

### Pseudocode

```python
if hasattr(user, "pro_connect") and len(user.pro_connect.siret) >= 9:
    siren = user.pro_connect.siret[:9]
    domain = user.email.split("@")[1] if user.email and "@" in user.email else None

    siren_org = Organization.objects.filter(siren=siren).first()
    domain_org = (
        Organization.objects.filter(email_domain=domain).first() if domain else None
    )

    # dédoublonnage si les deux pointent la même orga
    candidates = []
    for o in (siren_org, domain_org):
        if o is not None and all(o.pk != c.pk for c in candidates):
            candidates.append(o)

    if len(candidates) == 0:
        org = _create_org_from_siren(siren)
    elif len(candidates) == 1:
        org = candidates[0]
        changed = []
        if not org.siren:
            org.siren = siren
            changed.append("siren")
        if domain and not org.email_domain:
            org.email_domain = domain
            changed.append("email_domain")
        if changed:
            org.save()  # re-déclenche link_organization_to_users
    else:
        org = siren_org  # priorité au même SIREN

    if org:
        _set_user_org(user, org)
        return
```

---

## Partie 2 — Outil de fusion dans l'admin Django

### Principe

Sur la page de détail d'une organisation (`change_form`), un bouton **« Fusionner »**.
L'organisation consultée est la **survivante (cible)** ; on choisit l'organisation à
**absorber**, on réconcilie les champs, on confirme.

### Parcours utilisateur

1. **Page détail orga** : bouton « Fusionner » (ajouté via un template
   `change_form` surchargé pour `OrganizationAdmin`, pointant vers une URL admin
   custom `merge/<cible_id>/`).
2. **Écran de fusion** (`GET merge/<cible_id>/`) :
   - Sélection de l'organisation à absorber (champ autocomplete, excluant la cible).
   - Une fois l'absorbée choisie, tableau de réconciliation **champ par champ** pour
     `name`, `short_name`, `siren`, `email_domain`, `managed_cities` : on affiche la
     valeur de la cible et celle de l'absorbée ; les champs **de la cible sont
     pré-remplis et éditables** (l'admin peut reprendre la valeur de l'absorbée ou
     saisir autre chose). On affiche aussi le nombre d'utilisateurs de chaque côté.
3. **Garde-fou SIREN** : si cible et absorbée ont chacune un `siren` **non vide et
   différent**, la fusion est **refusée** avec un message d'erreur (deux entités
   légales distinctes — fusion probablement erronée). Ce contrôle s'applique sur les
   valeurs d'origine des deux orgas, indépendamment de ce que l'admin a saisi.
4. **Confirmation** (`POST`) : récapitulatif + bouton valider. À la validation, dans
   une transaction atomique :
   1. `UserProfile.objects.filter(organization=absorbée).update(organization=cible)`
      (un utilisateur n'a qu'un profil → pas de doublon d'utilisateur possible).
   2. Application des valeurs de champs choisies sur la cible.
   3. Suppression de l'organisation absorbée.
   4. `cible.save()` pour re-jouer le linking (`link_organization_to_users`).
   5. `messages.success(...)` récapitulant le nombre d'utilisateurs déplacés et le nom
      de l'orga supprimée ; redirection vers la page détail de la cible.

### Ordre des opérations (important)

On déplace les profils **avant** de supprimer l'absorbée (sinon `on_delete=SET_NULL`
mettrait les `organization` à `NULL`). On supprime l'absorbée **avant** d'écrire le
`siren`/`email_domain` choisi sur la cible, pour éviter un conflit d'unicité si la
valeur retenue provient de l'absorbée.

### Implémentation admin

- URL custom enregistrée via `OrganizationAdmin.get_urls()` (override propre à la
  ModelAdmin, à préférer au monkey-patch global `admin.site.get_urls` utilisé
  ailleurs dans ce fichier).
- Vue protégée par `self.admin_site.admin_view(...)` et `has_change_permission`.
- Templates dans `app/batid/templates/admin/` (formulaire de fusion + confirmation).
- Le garde-fou et la réconciliation sont validés côté serveur (ne pas se fier au
  formulaire seul).

---

## Tests

Commande : `docker exec web python manage.py test`. Pendant le dev, ne lancer que les
tests des fichiers concernés.

### `app/batid/tests/test_organization_service.py`

- **Adoption SIREN par orga email_domain sans SIREN** : une orga a `email_domain` =
  domaine de l'utilisateur et `siren` vide ; un user ProConnect avec ce domaine arrive
  → il est rattaché à cette orga, l'orga reçoit le SIREN, le `name` est inchangé,
  aucune nouvelle orga créée.
- **Adoption email_domain par orga SIREN sans domaine** : orga avec le bon `siren` et
  `email_domain` vide → reçoit le domaine de l'email.
- **Un seul candidat déjà complet** : orga avec le bon siren ET le bon domaine →
  rattachement sans modification.
- **Deux candidats distincts** : une orga porte le SIREN, une autre le domaine → user
  rattaché à celle du SIREN, aucune des deux modifiée, pas de création.
- **Zéro candidat** : aucune orga ne matche → création depuis l'INSEE (comportement
  actuel, INSEE mocké).
- **Pas d'écrasement** : orga candidate dont le `email_domain` est déjà renseigné (et
  différent) → non modifié.

### `app/batid/tests/test_admin.py`

- **Fusion nominale** : 2 orgas avec des users de part et d'autre → après fusion, tous
  les `UserProfile` pointent la cible, l'absorbée est supprimée, message de succès.
- **Blocage SIREN différents** : cible et absorbée ont des SIREN non vides différents →
  fusion refusée, aucune donnée modifiée.
- **Réconciliation champ par champ** : l'admin reprend l'`email_domain` de l'absorbée
  pour la cible → valeur correctement appliquée après suppression de l'absorbée (pas de
  conflit d'unicité).
- **Enrichissement d'un champ vide** : cible sans SIREN, absorbée avec SIREN → la cible
  récupère le SIREN choisi.

---

## Hors périmètre (YAGNI)

- Pas de détection/fusion automatique des doublons existants (uniquement l'outil manuel).
- Pas de fusion de plus de deux orgas à la fois.
- Pas de modification de la branche « email domain » du fallback non-ProConnect.
