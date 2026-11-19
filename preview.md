# Aperçu du passage du 19/11/2026 (rattrapage, dry_run)

Places : 5 − 1 ticket ouvert (#1254) = 4.

## Tickets que la boucle ouvrirait

1. `api-doc-contract-mismatch` : 27 occurrences dans 8 PR, dernière le 2026-11-18
2. `comment-not-in-english` : 6 occurrences dans 6 PR, dernière le 2026-09-15
3. `typo-in-code-text` : 7 occurrences dans 5 PR, dernière le 2026-01-20
4. `sandbox-command-committed` : 3 occurrences dans 3 PR, dernière le 2026-02-11

## Familles éligibles en attente de place

- `print-in-app-code` : 4 occurrences dans 3 PR, dernière le 2026-01-27
- `test-real-datetime` : 4 occurrences dans 2 PR, dernière le 2026-03-17

## Tickets existants rattachés

- `building-direct-write` → #1254 (marqueur trouvé). Aucune occurrence nouvelle par rapport au ticket : aucun commentaire.

## Corps des tickets

### [PR review loop] Doc OpenAPI contredite par le comportement de l'API

````markdown
<!-- pr-review-loop family=api-doc-contract-mismatch -->
## Erreur récurrente

La documentation OpenAPI d'un endpoint annonce des codes de statut, des cas de refus, des types ou des exemples de requête que l'API réelle contredit (code non documenté, exemple refusé, type faux).

## Occurrences (27 commentaires dans 8 PR)

- PR #562 · `leonkenneth` · 2025-02-27 · [commentaire](https://github.com/fab-geocommuns/RNB-coeur/pull/562#discussion_r1973275996) · `app/api_alpha/views.py`
  > J'imagine qu'on a aussi une 404 si le bâtiment en lui-même n'a pas été trouvé par exemple ?
- PR #562 · `leonkenneth` · 2025-02-27 · [commentaire](https://github.com/fab-geocommuns/RNB-coeur/pull/562#discussion_r1973841201) · `app/api_alpha/views.py`
  > suggestion : "description": "ID-RNB inconnu ou une clé d'interopérabilité n'a pas été trouvée auprès de la BAN"
- PR #562 · `leonkenneth` · 2025-02-27 · [commentaire](https://github.com/fab-geocommuns/RNB-coeur/pull/562#discussion_r1973841799) · `app/api_alpha/views.py`
  > suggestion : "description": "ID-RNB inconnu ou une clé d'interopérabilité n'a pas été trouvée auprès de la BAN"
- PR #562 · `leonkenneth` · 2025-02-27 · [commentaire](https://github.com/fab-geocommuns/RNB-coeur/pull/562#discussion_r1973842346) · `app/api_alpha/views.py`
  > suggestion : "description": "ID-RNB inconnu ou une clé d'interopérabilité n'a pas été trouvée auprès de la BAN"
- PR #581 · `fchabouis` · 2025-03-27 · [commentaire](https://github.com/fab-geocommuns/RNB-coeur/pull/581#discussion_r2016895837) · `app/api_alpha/utils/rnb_doc.py`
  > Pour info, j'avais mis la 503 quand le endpoint fait potentiellement appel à l'API de la BAN (création de bâtiment par exemple) et pour gérer les indisponibilités de leur côté (si la BAN est indisp…
- PR #709 · `fchabouis` · 2025-09-15 · [commentaire](https://github.com/fab-geocommuns/RNB-coeur/pull/709#discussion_r2349228658) · `app/api_alpha/endpoints/buildings/list_create_buildings.py`
  > Si on demande aux personnes de mettre 1, techniquement le champ n'est pas un booléen mais un `integer`.
- PR #1154 · `ThomasDos` · 2026-10-30 · [commentaire](https://github.com/fab-geocommuns/RNB-coeur/pull/1154#discussion_r4422013202) · `app/api_alpha/utils/rnb_doc.py`
  > L'anneau de l'exemple contient deux fois le même point. Ce n'est pas un polygone valide : GeoJSON demande au moins 4 positions, la première égale à la dernière, et GEOS refuse de le construire (« I…
- PR #1190 · `ThomasDos` · 2026-11-05 · [commentaire](https://github.com/fab-geocommuns/RNB-coeur/pull/1190#discussion_r4478793271) · `app/api_alpha/endpoints/buildings/get_diff.py`
  > Une date future ne renvoie pas d'erreur : `since=2099-01-01T00:00:00Z` donne un 200 avec un fichier vide, sans en-tête. C'est pareil pour une date égale à la dernière modification du RNB, donc un c…
- PR #1190 · `ThomasDos` · 2026-11-05 · [commentaire](https://github.com/fab-geocommuns/RNB-coeur/pull/1190#discussion_r4478793284) · `app/api_alpha/endpoints/buildings/get_diff.py`
  > Ce sont des objets, pas de simples identifiants. Exemple réel : `{"id": "BATIMENT0000000288564165", "source": "bdtopo", "created_at": "2023-12-21T20:47:57.150660+00:00", "source_version": "bdtopo_2…
- PR #1190 · `ThomasDos` · 2026-11-05 · [commentaire](https://github.com/fab-geocommuns/RNB-coeur/pull/1190#discussion_r4478793294) · `app/api_alpha/endpoints/buildings/get_diff.py`
  > Une date qui n'existe pas renvoie une erreur 500, pas ce 400. Exemple : `since=2026-02-30T00:00:00Z`. La lecture de la date lève une `ValueError` que rien n'attrape. Le bug existait avant la PR, ma…
- PR #1192 · `ThomasDos` · 2026-11-05 · [commentaire](https://github.com/fab-geocommuns/RNB-coeur/pull/1192#discussion_r4479178099) · `app/api_alpha/utils/rnb_doc.py`
  > Les lectures répondent aussi 401 avec un token invalide, et aucune ne le documente. Sur `GET /api/alpha/buildings/QBAAG16VCJWA/`, sans en-tête : 200. Avec `Authorization: Token invalide` : 401 « To…
- PR #1192 · `ThomasDos` · 2026-11-05 · [commentaire](https://github.com/fab-geocommuns/RNB-coeur/pull/1192#discussion_r4479178154) · `app/api_alpha/utils/rnb_doc.py`
  > GitBook n'ajoute pas de préfixe à un `apiKey` : ses exemples afficheront `Authorization: YOUR_API_KEY`, et sans `Token` une écriture répond 401. [Doc GitBook](https://gitbook.com/docs/api-reference…
- PR #1191 · `ThomasDos` · 2026-11-05 · [commentaire](https://github.com/fab-geocommuns/RNB-coeur/pull/1191#discussion_r4479716913) · `app/api_alpha/endpoints/buildings/single_building.py`
  > L'exemple de requête que GitBook génère depuis ce schéma reste refusé : `is_active: true` avec `status`, `shape: "text"` et `is_valid: true` répond 400. À ajouter à côté de `schema` (ligne 201), le…
- PR #1191 · `ThomasDos` · 2026-11-05 · [commentaire](https://github.com/fab-geocommuns/RNB-coeur/pull/1191#discussion_r4479716925) · `app/api_alpha/views.py`
  > Même problème : l'exemple généré envoie `merge_existing_addresses: true` avec une liste d'adresses, l'API répond 400. À ajouter à côté de `schema` : python "example": { "comment": "un seul et même …
- PR #1191 · `ThomasDos` · 2026-11-05 · [commentaire](https://github.com/fab-geocommuns/RNB-coeur/pull/1191#discussion_r4479716935) · `app/api_alpha/views.py`
  > GitBook ignore `minItems` : l'exemple généré ne contient qu'un bâtiment, l'API répond 400. À ajouter à côté de `schema`, avec deux géométries distinctes : python "example": { "comment": "deux bâtim…
- PR #1191 · `ThomasDos` · 2026-11-05 · [commentaire](https://github.com/fab-geocommuns/RNB-coeur/pull/1191#discussion_r4479716943) · `app/api_alpha/utils/rnb_doc.py`
  > Un bâtiment actif démoli ne compte pas (le recouvrir répond 201), le bâtiment modifié ou scindé non plus. À l'inverse, un point dans un bâtiment construit répond 400. suggestion : f"ne pas recouvri…
- PR #1191 · `ThomasDos` · 2026-11-05 · [commentaire](https://github.com/fab-geocommuns/RNB-coeur/pull/1191#discussion_r4479716961) · `app/api_alpha/endpoints/buildings/single_building.py`
  > `{"comment": "x"}` répond aussi 400. suggestion : * le corps est vide ou ne contient que `comment`, ou combine `is_active` avec `status`, `addresses_cle_interop`, `shape` ou `is_valid` ;
- PR #1191 · `ThomasDos` · 2026-11-05 · [commentaire](https://github.com/fab-geocommuns/RNB-coeur/pull/1191#discussion_r4479716967) · `app/api_alpha/endpoints/buildings/single_building.py`
  > `{"status": "constructed"}` sur un bâtiment inactif déjà `constructed` répond 204. suggestion : * le bâtiment est inactif et la requête ne demande pas sa réactivation (une requête qui ne change rie…
- PR #1191 · `ThomasDos` · 2026-11-05 · [commentaire](https://github.com/fab-geocommuns/RNB-coeur/pull/1191#discussion_r4479716982) · `app/api_alpha/endpoints/buildings/single_building.py`
  > Il manque ce refus : la clé de voie `75105_8884` et la clé de commune `75105` répondent 400. À ajouter aussi à la création (`list_create_buildings.py:228`), à la fusion (`views.py:366`) et à la sci…
- PR #1191 · `ThomasDos` · 2026-11-05 · [commentaire](https://github.com/fab-geocommuns/RNB-coeur/pull/1191#discussion_r4479716997) · `app/api_alpha/views.py`
  > `false` avec une liste répond 201, `true` avec `[]` aussi, et `false` sans liste répond 400. suggestion : * `addresses_cle_interop` est absent alors que `merge_existing_addresses` n'est pas à `true…
- PR #1191 · `ThomasDos` · 2026-11-05 · [commentaire](https://github.com/fab-geocommuns/RNB-coeur/pull/1191#discussion_r4479717007) · `app/api_alpha/views.py`
  > `merge_existing_addresses: true` avec `[]` répond 201 et le nouveau bâtiment garde les adresses des parents. Ligne 394, écrire « ne doit alors contenir aucune adresse ». Ligne 359, retirer « , mais…
- PR #1191 · `ThomasDos` · 2026-11-05 · [commentaire](https://github.com/fab-geocommuns/RNB-coeur/pull/1191#discussion_r4479717022) · `app/api_alpha/endpoints/buildings/list_create_buildings.py`
  > BAN injoignable : l'API répond 500 aujourd'hui (#1111). Le 503 ne tombe que si la BAN répond en erreur, par exemple 502. Même texte à `single_building.py:277`, `views.py:436` et `views.py:614`. sug…
- PR #1191 · `ThomasDos` · 2026-11-05 · [commentaire](https://github.com/fab-geocommuns/RNB-coeur/pull/1191#discussion_r4479717034) · `app/api_alpha/endpoints/buildings/list_create_buildings.py`
  > Ligne 291 : `plots` n'est jamais dans le 201 du POST. Sans décision de renvoyer les parcelles, retirer `BuildingWPlots` ici et `with_plots=True` ligne 365, sans effet.
- PR #1191 · `ThomasDos` · 2026-11-10 · [commentaire](https://github.com/fab-geocommuns/RNB-coeur/pull/1191#discussion_r4524011391) · `app/api_alpha/utils/rnb_doc.py`
  > Une ligne peut passer : `LINESTRING(-27 45, -26.999 45, -26.999 45.001)` répond 201, une `MULTILINESTRING` aussi. L'ancienne formulation était exacte : suggestion : f"pour un polygone ou un multipo…
- PR #1191 · `ThomasDos` · 2026-11-10 · [commentaire](https://github.com/fab-geocommuns/RNB-coeur/pull/1191#discussion_r4524011413) · `app/api_alpha/views.py`
  > Deux bâtiments créés identiques au statut `demolished` répondent 201. Le cas réellement refusé est déjà couvert par la règle du champ `shape` (un autre bâtiment `constructed` ou `notUsable`). sugge…
- PR #1224 · `ThomasDos` · 2026-11-18 · [commentaire](https://github.com/fab-geocommuns/RNB-coeur/pull/1224#discussion_r4617118969) · `app/api_alpha/views.py`
  > `?q=ab` renvoie 503 alors que la BAN fonctionne. La BAN refuse les adresses de moins de 3 caractères, et le code renvoie 503 pour toute réponse en erreur de la BAN. Proposition : « La BAN a répondu…
- PR #1224 · `ThomasDos` · 2026-11-18 · [commentaire](https://github.com/fab-geocommuns/RNB-coeur/pull/1224#discussion_r4617118980) · `app/api_alpha/endpoints/buildings/intersect.py`
  > `limit=0` renvoie 400, mais la liste des 400 de cet endpoint (ligne 91) ne le mentionne pas. Il y manque aussi le polygone dans une autre projection que WGS84 (`SRID=2154;POLYGON(...)`). Propositio…

## Contrôle envisagé

Tests de contrat en CI : chaque exemple de requête de la doc doit être accepté, et un outil comme schemathesis signale les codes de statut non documentés et les erreurs 500.

Voir aussi l'epic #1122, qui remet la doc en phase avec le code sans empêcher les écarts de revenir.

## Décision

- Fermer comme **terminé** quand le contrôle est en place.
- Fermer comme **not planned** si cette erreur ne doit pas devenir un contrôle, avec la raison en commentaire : la boucle ne la reproposera plus.

Ticket ouvert par la boucle de review des PR, voir `docs/review-rules/LOOP.md`.
````

### [PR review loop] Commentaire de code en français

````markdown
<!-- pr-review-loop family=comment-not-in-english -->
## Erreur récurrente

Un commentaire ou une docstring est écrit en français alors que la convention du dépôt est l'anglais.

## Occurrences (6 commentaires dans 6 PR)

- PR #357 · `fchabouis` · 2024-03-29 · [commentaire](https://github.com/fab-geocommuns/RNB-coeur/pull/357#discussion_r1544334354) · `app/batid/services/guess_bdg_new.py`
  > J'aimerais bien qu'on choisisse une langue pour les commentaires :) L'une ou l'autre me vont, mais peut-être pas les deux à la fois ?
- PR #439 · `fchabouis` · 2024-08-02 · [commentaire](https://github.com/fab-geocommuns/RNB-coeur/pull/439#discussion_r1701765833) · `app/api_alpha/tests/test_ads.py`
  > suggestion : "email": "", # This user is already created in the setUp() function without an email. If the user already exists it is returned without being updated. }, Je suis un peu pénible 😬 tous …
- PR #817 · `fchabouis` · 2026-01-27 · [commentaire](https://github.com/fab-geocommuns/RNB-coeur/pull/817#discussion_r2731348764) · `app/batid/tests/test_report_arcep.py`
  > il y a un mélange de Français et d'Anglais dans les commentaires
- PR #973 · `fchabouis` · 2026-07-28 · [commentaire](https://github.com/fab-geocommuns/RNB-coeur/pull/973#discussion_r3666427417) · `app/api_alpha/tests/buildings/test_intersect.py`
  > il y a des commentaires en Français et en Anglais dans cette PR, on a l'habitude de tous les écrire en Anglais.
- PR #976 · `fchabouis` · 2026-07-29 · [commentaire](https://github.com/fab-geocommuns/RNB-coeur/pull/976#discussion_r3674806940) · `app/batid/services/data_fix/fill_empty_event_id.py`
  > commentaires en français à traduire
- PR #1026 · `pauletienney` · 2026-09-15 · [commentaire](https://github.com/fab-geocommuns/RNB-coeur/pull/1026#discussion_r4013889086) · `app/batid/models/others.py`
  > suggestion : # non-unique. The uniqueness is real and enforced at the DB level. # Quand le internal_id sera devenue une PK, alors il faudra supprimer ce code.

## Contrôle envisagé

Script CI détectant les commentaires et docstrings contenant des mots français ou des caractères accentués.

## Décision

- Fermer comme **terminé** quand le contrôle est en place.
- Fermer comme **not planned** si cette erreur ne doit pas devenir un contrôle, avec la raison en commentaire : la boucle ne la reproposera plus.

Ticket ouvert par la boucle de review des PR, voir `docs/review-rules/LOOP.md`.
````

### [PR review loop] Faute d'orthographe dans un commentaire ou un message du code

````markdown
<!-- pr-review-loop family=typo-in-code-text -->
## Erreur récurrente

Un commentaire, une docstring ou un message d'erreur contient une faute de frappe (lettre en trop, mot répété).

## Occurrences (7 commentaires dans 5 PR)

- PR #215 · `fchabouis` · 2023-10-17 · [commentaire](https://github.com/fab-geocommuns/RNB-coeur/pull/215#discussion_r1361703420) · `app/batid/tests/test_village.py`
  > petite typo ici (and and)
- PR #709 · `leonkenneth` · 2025-09-15 · [commentaire](https://github.com/fab-geocommuns/RNB-coeur/pull/709#discussion_r2348903054) · `app/api_alpha/tests/buildings/test_pagination.py`
  > suggestion : # Since the data as no explicit ORDER BY we want to check the results have a consistent order
- PR #709 · `leonkenneth` · 2025-09-15 · [commentaire](https://github.com/fab-geocommuns/RNB-coeur/pull/709#discussion_r2348903432) · `app/api_alpha/tests/buildings/test_pagination.py`
  > suggestion : # Since the data as no explicit ORDER BY we want to check the results have a consistent order
- PR #709 · `leonkenneth` · 2025-09-15 · [commentaire](https://github.com/fab-geocommuns/RNB-coeur/pull/709#discussion_r2348904212) · `app/api_alpha/tests/buildings/test_pagination.py`
  > suggestion : # Since the data as no explicit ORDER BY we want to check the results have a consistent order
- PR #744 · `leonkenneth` · 2025-11-28 · [commentaire](https://github.com/fab-geocommuns/RNB-coeur/pull/744#discussion_r2571152062) · `app/batid/models/building.py`
  > suggestion : "A building deactivation involves exactly one building."
- PR #800 · `leonkenneth` · 2026-01-05 · [commentaire](https://github.com/fab-geocommuns/RNB-coeur/pull/800#discussion_r2661411230) · `app/api_alpha/serializers/serializers.py`
  > suggestion : # virtual user to compare with the password for similarity checks
- PR #812 · `fchabouis` · 2026-01-20 · [commentaire](https://github.com/fab-geocommuns/RNB-coeur/pull/812#discussion_r2708475230) · `app/batid/services/guess_bdg_new.py`
  > suggestion : # Transform any multiple space into single space

## Contrôle envisagé

codespell en pre-commit et en CI.

## Décision

- Fermer comme **terminé** quand le contrôle est en place.
- Fermer comme **not planned** si cette erreur ne doit pas devenir un contrôle, avec la raison en commentaire : la boucle ne la reproposera plus.

Ticket ouvert par la boucle de review des PR, voir `docs/review-rules/LOOP.md`.
````

### [PR review loop] Commande sandbox.py embarquée dans une PR

````markdown
<!-- pr-review-loop family=sandbox-command-committed -->
## Erreur récurrente

La commande de brouillon app/batid/management/commands/sandbox.py, censée rester vide, est committée avec du code d'essai.

## Occurrences (3 commentaires dans 3 PR)

- PR #451 · `bbaret` · 2024-08-13 · [commentaire](https://github.com/fab-geocommuns/RNB-coeur/pull/451#discussion_r1714839995) · `app/batid/management/commands/sandbox.py`
  > A supprimer car cela ressemble à ton fichier de test pour notre soucis de GEOS :)
- PR #566 · `bbaret` · 2025-03-14 · [commentaire](https://github.com/fab-geocommuns/RNB-coeur/pull/566#discussion_r1995725871) · `app/batid/management/commands/sandbox.py`
  > A supprimer
- PR #829 · `fchabouis` · 2026-02-11 · [commentaire](https://github.com/fab-geocommuns/RNB-coeur/pull/829#discussion_r2794323812) · `app/batid/management/commands/sandbox.py`
  > changement à supprimer

## Contrôle envisagé

Contrôle pre-commit ou CI qui refuse toute modification de sandbox.py par rapport à sa version vide.

## Décision

- Fermer comme **terminé** quand le contrôle est en place.
- Fermer comme **not planned** si cette erreur ne doit pas devenir un contrôle, avec la raison en commentaire : la boucle ne la reproposera plus.

Ticket ouvert par la boucle de review des PR, voir `docs/review-rules/LOOP.md`.
````

