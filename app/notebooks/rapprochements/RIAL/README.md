# POC RIAL : relier un ID RNB aux locaux fiscaux

Issue : [#1133](https://github.com/fab-geocommuns/RNB-coeur/issues/1133). Contexte interne : dossier Notion « Chantier RIAL ».

RIAL (Répertoire Inter-Administratif des Locaux) est l'API de la DGFiP qui donne les locaux fiscaux d'une adresse ou d'une parcelle. Elle ne connaît pas les bâtiments : ce POC part d'un ID RNB, en déduit les adresses BAN et la parcelle principale, puis les recherches RIAL à lancer.

## Fichiers

| Fichier | Rôle |
|---|---|
| `rial_requests.py` | cœur du POC : un ID RNB donne la liste des requêtes RIAL, avec le motif de chaque adresse ou parcelle écartée |
| `fetch_communes.py` | télécharge les bâtiments RNB des 3 communes du bac à sable et le nombre de locaux par commune dans `data/` |
| `analyze.py` | mesure la part des bâtiments rattachables sans ambiguïté |

```bash
cd app/notebooks/rapprochements/RIAL
python rial_requests.py VA4FVBKD7DHH 7JT1THHYM9HB   # vérifications, puis requêtes générées
python fetch_communes.py                            # environ 400 appels à l'API RNB publique
python analyze.py
```

Aucune dépendance hors bibliothèque standard. Aucun appel à RIAL n'est fait : il manque l'accès.

## Accès

Demande DataPass D100173 (bac à sable), déposée le 28/10/2026 depuis le compte DINUM de Thomas, en cours d'instruction. L'IP déclarée est celle du serveur de staging du RNB (voir `scw instance server list`) : les appels RIAL doivent partir de ce serveur.

Le bac à sable ne couvre que Aulnay-sous-Bois (93005), Ajaccio (2A004) et Pointe-à-Pitre (97120). Adresses et parcelles réelles, identifiants de locaux fictifs.

## Contrat de l'API

Source : [spécification OpenAPI](https://raw.githubusercontent.com/betagouv/api_gouv_swaggers/refs/heads/main/swaggers/api-rial.json) et [documentation fonctionnelle v2026-05](https://www.impots.gouv.fr/sites/default/files/media/1_metier/stats_et_donnees/api/docs-fonctionnelles-cgu/api-rial-documentation-fonctionnelle-v2026-05.pdf).

| Route (GET, base `/rial/v1`) | Paramètres | Réponse |
|---|---|---|
| `/locaux/adresseTopographique` | `codeDepartementInsee`, `codeCommuneInsee`, `codeVoieTopo`, `numeroVoirie`, `indiceRepetitionNumeroVoirie` (option) | `listeIdentifiantsFiscaux` |
| `/locaux/parcelleCadastrale` | `codeDepartementInsee`, `codeCommuneCadastral`, `codeCommuneAbsorbee` (option), `codeSectionParcelle`, `numeroPlanParcelle` | `listeIdentifiantsFiscaux` |
| `/locaux/{ids}` | jusqu'à 200 identifiants de 12 caractères, séparés par des virgules | adresse, parcelle, bâtiment DGFiP (lettre), entrée, étage, porte, nature, surfaces, état |
| `/etatSante` | aucun | disponibilité |

Authentification : jeton OAuth2 `client_credentials` obtenu sur `https://gw.dgfip.finances.gouv.fr/token` (identifiant et secret en Basic). Chaque appel porte `Authorization: Bearer <jeton>` et `X-Correlation-ID: <uuid>`. La passerelle filtre aussi l'IP appelante. URL du bac à sable : communiquée avec l'accès.

Quota : 50 appels par minute par défaut. Pas de pagination : au delà de 500 locaux trouvés, refus en 403.

Codes métier utiles : `90` aucun résultat (404), `91` et `92` trop de locaux (403), `01` identifiant inconnu, `02` local en cours d'évaluation, `26` code voie invalide.

## Conversion RNB vers RIAL

Appliquée par `rial_requests.py` et couverte par ses vérifications :

* tous les critères en majuscules ;
* département sur 2 caractères (3 pour les DOM : `971`), `codeCommuneInsee` sur 3 (2 pour les DOM) ;
* `codeCommuneCadastral` toujours sur 3 caractères, DOM compris (`97120` donne `120`) ;
* clé BAN `93005_3470_00004_bis` : voie `3470`, numéro `4`, indice `B` (`ter` `T`, `quater` `Q`, `quinquies` `C`, une lettre seule passe en majuscule) ;
* code de voie provisoire de la BAN (6 caractères, ex. `mmh9r0`) : adresse écartée, RIAL répond `26` ;
* numéro `99999` (lieu-dit sans numéro) : adresse écartée ;
* parcelle `93005000BK0174` : section `BK`, plan `0174` ; préfixe différent de `000` : `codeCommuneAbsorbee` ; section `0A` : `A` ;
* parcelle principale : celle qui couvre au moins 50 % du bâtiment.

À vérifier avec l'accès : le sens de `codeTypeLocal` (la doc et l'OpenAPI inversent maison et appartement) et la forme de `descriptifHabitation` (objet ou liste).

## Résultats au 28/10/2026

| | Aulnay 93005 | Ajaccio 2A004 | Pointe-à-Pitre 97120 |
|---|---:|---:|---:|
| Bâtiments RNB actifs | 21 297 | 12 985 | 3 769 |
| Avec au moins une adresse | 82,6 % | 48,9 % | 0,0 % |
| Adresses au code voie TOPO | 95,1 % | 66,9 % | 0 sur 1 |
| Rattachables sans ambiguïté | 53,1 % | 29,8 % | 46,0 % |
| Appels RIAL pour la commune | 29 051 | 9 029 | 2 384 |

« Sans ambiguïté » : seul bâtiment RNB de la commune sur une adresse utilisable, ou seul à couvrir au moins 50 % de sa parcelle principale.

## Prochaine étape

Une fois l'accès obtenu : brancher le jeton dans un client qui exécute les requêtes de `rial_requests_for()`, lancer sur les 3 communes depuis le serveur de staging, relever le taux de réponses `90`, `26` et `403` et le nombre de locaux par recherche.
