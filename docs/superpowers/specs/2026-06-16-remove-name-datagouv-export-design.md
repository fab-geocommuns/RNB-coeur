# Retrait du nom/prénom de l'export data.gouv

Date : 2026-06-16

## Contexte

La branche `remove_firstlast_name` (mergée via PR #942, commit `aa4602ae`) a cessé
d'**exposer** le nom et le prénom des utilisateurs : partout où un `display_name`
était construit à partir de `first_name`/`last_name`, il vaut désormais le `username`.
Les points traités étaient `PublicUserSerializer`, `bdg_history.py` et
`batid/services/user.py::get_display_name`.

Un point d'exposition a été oublié : l'export vers data.gouv, qui construit encore
`display_name` à partir du nom et du prénom dans le bloc `validated_by`.

## Objectif

Suivre la même logique pour l'export data.gouv : `display_name` doit valoir le
`username`, sans plus jamais dériver du nom/prénom.

**Hors périmètre** : la collecte et le stockage du nom/prénom restent inchangés
(création de compte API, ProConnect, recherche admin). Décision validée avec
l'utilisateur le 2026-06-16.

## Changement

Fichier : `app/batid/services/data_gouv_publication.py`, bloc `validated_by`
(actuellement lignes 99-104).

Avant :

```sql
'display_name',
case
    when u.last_name is not null and u.last_name <> ''
    then u.first_name || ' ' || substring(u.last_name, 1, 1) || '.'
    else u.first_name
end,
```

Après (même commentaire que dans la branche) :

```sql
-- We deliberately no longer expose first/last name: display_name is the username
'display_name', u.username,
```

## Tests

Fichier : `app/batid/tests/test_data_gouv_publication.py`.

Les `display_name` attendus dans `validated_by` changent :

- `"El V."` → `"el_validator"`
- `"Jean D."` → `"jean_doux"`

## Vérification

`docker exec web python manage.py test` sur la classe de test de l'export data.gouv.
