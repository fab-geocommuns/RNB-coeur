# Spec : Mise à jour de la table Address depuis la BAN

## Contexte

Un certain nombre d'adresses en base ont des clés d'interopérabilité (`Address.id`) périmées.
Un nouvel identifiant existe : le `ban_id` (UUID). Les champs textuels (`street`, `city_name`)
ne contiennent actuellement ni accent ni majuscule, alors qu'ils le devraient.

**Objectif** : toutes les adresses sont à jour (plus de clé d'interop périmée), le `ban_id` est
renseigné quand disponible, les champs textuels ont les bons accents/majuscules — le tout sans
casser le lien bâtiment-adresse existant (`Building.addresses_id`).

## Source de données

Fichier BAN `csv-with-ids` par département :
`https://adresse.data.gouv.fr/data/ban/adresses/latest/csv-with-ids/adresses-with-ids-{dpt}.csv.gz`

Contient : `id` (clé d'interop), `id_ban_adresse` (UUID), `nom_voie`, `nom_commune`, et tous
les autres champs textuels. Séparateur : `;`.

## Arbre de décision

```
Address en base
│
├─ Clé d'interop existe dans le fichier BAN (still_exists=True)
│  │
│  ├─ Texte normalisé identique → MAJ accents/majuscules (street, city_name) + ban_id
│  │
│  └─ Texte normalisé différent → Flag "text_mismatch"
│
└─ Clé d'interop n'existe plus (still_exists=False)
   │
   ├─ Adresse NON liée à un bâtiment (absente de BuildingWithHistory.addresses_id)
   │  → Suppression
   │
   └─ Adresse liée à un bâtiment
      │
      ├─ Géocodage réussi (bon score) → MAJ clé d'interop (PK) + MAJ Building.addresses_id + ban_id
      │
      └─ Géocodage échoué → Flag "not_found"
```

## Comparaison textuelle

Normalisation : `strip()` + `lower()` + suppression des accents via
`unicodedata.normalize('NFD')` puis suppression des caractères de catégorie `Mn`.

On compare les versions normalisées de `street` vs `nom_voie` et `city_name` vs `nom_commune`.

- Si identiques après normalisation → mise à jour avec la version BAN (accents + majuscules).
- Si différentes → flag `text_mismatch` pour investigation.

> **Phase future** : un fuzzy match sera appliqué sur les adresses flaggées `text_mismatch`
> pour récupérer les cas de différences mineures (typos, abréviations).

## Champ de flag temporaire

Ajout d'un champ `ban_update_flag` sur le modèle `Address` :

- `CharField(max_length=20, null=True, default=None, db_index=True)`
- Valeurs possibles :
  - `None` : non traité ou traité avec succès
  - `"text_mismatch"` : clé existe dans la BAN mais le texte normalisé diffère
  - `"not_found"` : adresse liée à un bâtiment, non retrouvée par géocodage

Ce champ est temporaire et sera supprimé une fois la migration terminée.

## Mise à jour de la clé d'interop (PK)

Quand on retrouve une adresse par géocodage avec une nouvelle clé d'interop :

1. Mise à jour de `Building.addresses_id` via SQL brut : remplacer l'ancienne clé par la
   nouvelle dans tous les tableaux `addresses_id` des bâtiments concernés.
2. Mise à jour de `Address.id` via SQL brut.
3. Le tout dans une même transaction.

Le trigger PostgreSQL existant sur `Building` se charge de mettre à jour
`BuildingAddressesReadOnly` automatiquement.

---

## Découpage en PRs

### PR 1 — Nettoyage du flagging `still_exists`

**Branche** : `ban_flag_outdated_cle_interop` (en cours)

**Contenu** :

- Retirer la mise à jour du champ `ban_id` de `flag_addresses_from_ban_file()`.
- Le rôle de cette fonction se limite désormais à :
  - Marquer `still_exists=True` les adresses dont la clé existe dans le fichier BAN.
  - Marquer `still_exists=False` les adresses du département absentes du fichier.
- Adapter les tests existants dans `test_update_addresses_ban.py`.

**Fichiers concernés** :

| Fichier | Modification |
|---------|-------------|
| `app/batid/services/imports/update_addresses_ban.py` | Retirer la logique ban_id |
| `app/batid/tests/test_update_addresses_ban.py` | Adapter les tests |

---

### PR 2 — MAJ textuelle et `ban_id` des adresses existantes (`still_exists=True`)

**Pré-requis** : PR 1 mergée, `still_exists` renseigné pour tous les départements.

**Contenu** :

1. **Migration** : ajout du champ `ban_update_flag` sur `Address`.

2. **Fonction de normalisation** (utilitaire) :
   - `normalize_text(text: str) -> str` : strip + lower + suppression accents.

3. **Nouvelle fonction** `update_addresses_text_and_ban_id(src_params, batch_size)` :
   - Lit le fichier BAN csv-with-ids du département.
   - Pour chaque adresse en base avec `still_exists=True` dont la clé est dans le fichier :
     - Compare `normalize_text(street)` vs `normalize_text(nom_voie)`
       et `normalize_text(city_name)` vs `normalize_text(nom_commune)`.
     - Si identique : met à jour `street` et `city_name` avec la version BAN +
       renseigne `ban_id` si présent dans le fichier.
     - Si différent : positionne `ban_update_flag = "text_mismatch"`.
   - Traitement par batch (`bulk_update`).

4. **Tâche Celery** pour lancer le traitement par département.

5. **Tests** :
   - Adresse `"rue de la republique"` vs BAN `"Rue de la République"` → MAJ + ban_id.
   - Adresse `"rue de la gare"` vs BAN `"Avenue Victor Hugo"` → flag `text_mismatch`.
   - Adresse sans `id_ban_adresse` dans le fichier BAN → MAJ texte uniquement, ban_id reste null.

**Fichiers concernés** :

| Fichier | Modification |
|---------|-------------|
| `app/batid/models/others.py` | Ajout champ `ban_update_flag` |
| `app/batid/migrations/XXXX_*.py` | Migration pour `ban_update_flag` |
| `app/batid/services/imports/update_addresses_ban.py` | Nouvelle fonction |
| `app/batid/tasks.py` | Nouvelle tâche Celery |
| `app/batid/tests/test_update_addresses_ban.py` | Nouveaux tests |

---

### PR 3 — Suppression des adresses obsolètes non liées à un bâtiment

**Pré-requis** : PR 1 mergée.

**Contenu** :

1. **Nouvelle fonction** `delete_unlinked_obsolete_addresses(batch_size)` :
   - Sélectionne les adresses avec `still_exists=False`.
   - Pour chaque adresse, vérifie si elle apparaît dans la colonne `addresses_id`
     de `BuildingWithHistory` (via requête sur la vue).
   - Si absente de tout bâtiment (actuel ou historique) → suppression.
   - Si liée à au moins un bâtiment → conservée (sera traitée en PR 4).

2. **Tâche Celery**.

3. **Tests** :
   - Adresse `still_exists=False` absente de `BuildingWithHistory` → supprimée.
   - Adresse `still_exists=False` présente dans `BuildingWithHistory.addresses_id` → conservée.

**Fichiers concernés** :

| Fichier | Modification |
|---------|-------------|
| `app/batid/services/imports/update_addresses_ban.py` | Nouvelle fonction |
| `app/batid/tasks.py` | Nouvelle tâche Celery |
| `app/batid/tests/test_update_addresses_ban.py` | Nouveaux tests |

---

### PR 4 — Géocodage et MAJ de la clé d'interop des adresses obsolètes liées

**Pré-requis** : PR 2 et PR 3 mergées.

**Contenu** :

1. **Nouvelle fonction** `geocode_and_update_obsolete_addresses(batch_size)` :
   - Sélectionne les adresses avec `still_exists=False` encore en base
     (= liées à un bâtiment, non supprimées par PR 3).
   - Pour chaque adresse, construit une adresse textuelle à partir des champs en base
     (`street_number`, `street_rep`, `street`, `city_zipcode`, `city_name`).
   - Appel à l'API de géocodage BAN :
     `https://api-adresse.data.gouv.fr/search/?q={adresse_textuelle}`.
   - Si le score de confiance est suffisant (seuil à définir, ex: >= 0.7) :
     - Dans une transaction SQL :
       - Met à jour `Building.addresses_id` (remplace ancienne clé par nouvelle)
         dans tous les bâtiments concernés.
       - Met à jour `Address.id` avec la nouvelle clé d'interop.
     - Renseigne `ban_id` si disponible dans la réponse.
     - Passe `still_exists` à `True`.
   - Si le score est insuffisant ou pas de résultat :
     - Positionne `ban_update_flag = "not_found"`.
   - **Rate limiting** : respecter les limites de l'API (pauses entre les requêtes).

2. **Tâche Celery**.

3. **Tests** (avec mock de l'API BAN) :
   - Géocodage avec bon score → MAJ PK + `addresses_id` + `ban_id` + `still_exists=True`.
   - Géocodage avec mauvais score → flag `"not_found"`.
   - Vérifier que `BuildingAddressesReadOnly` est synchronisé après la MAJ
     (trigger PostgreSQL).

**Fichiers concernés** :

| Fichier | Modification |
|---------|-------------|
| `app/batid/services/imports/update_addresses_ban.py` | Nouvelle fonction |
| `app/batid/tasks.py` | Nouvelle tâche Celery |
| `app/batid/tests/test_update_addresses_ban.py` | Nouveaux tests |

---

### PR future — Fuzzy match sur les `text_mismatch`

**Pré-requis** : PR 2 mergée et exécutée.

- Reprendre les adresses avec `ban_update_flag = "text_mismatch"`.
- Appliquer un fuzzy match (ex: `rapidfuzz`) avec un seuil à définir.
- Mettre à jour les adresses suffisamment similaires.
- Conserver le flag pour les cas restants.

---

## Résumé

| PR | Contenu | Dépendances | Parallélisable |
|----|---------|-------------|----------------|
| 1  | Nettoyage flagging `still_exists` (retrait ban_id) | — | — |
| 2  | MAJ textuelle + ban_id (`still_exists=True`) + champ flag | PR 1 | Oui avec PR 3 |
| 3  | Suppression adresses obsolètes non liées | PR 1 | Oui avec PR 2 |
| 4  | Géocodage + MAJ clé d'interop (`still_exists=False` liées) | PR 2, PR 3 | — |
| future | Fuzzy match sur `text_mismatch` | PR 2 | — |
