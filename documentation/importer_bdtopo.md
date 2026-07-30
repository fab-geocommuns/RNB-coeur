# Importer la BD TOPO dans le RNB

## Résumé

La BD TOPO est la base de données topographique de l'IGN. Elle contient, entre autres, la description et la géométrie de tous les bâtiments de France. C'est l'une des sources principales qui alimentent le RNB.

L'import de la BD TOPO consiste à :

1. télécharger, pour chaque département, le fichier de bâtiments publié par l'IGN ;
2. transformer chaque bâtiment de ce fichier en **candidat** : une ligne en attente d'examen, stockée dans une table dédiée ;
3. **inspecter** chaque candidat, c'est-à-dire le comparer aux bâtiments déjà présents dans le RNB pour décider s'il faut créer un nouveau bâtiment, compléter un bâtiment existant, ou ne rien faire.

L'import est automatique en production, quatre fois par an. L'inspection des candidats, elle, doit être lancée à la main après chaque import (voir plus bas).

## Calendrier

**Publication de la BD TOPO.** L'IGN produit une nouvelle version (un « millésime ») quatre fois par an : les 15 mars, 15 juin, 15 septembre et 15 décembre. Ces dates sont des dates de production internes à l'IGN ; les fichiers ne sont réellement téléchargeables que 3 à 4 semaines plus tard, avec un délai variable.

**Import dans le RNB.** Pour tenir compte de ce délai, l'import automatique est programmé environ un mois après chaque millésime : les **15 janvier, 15 avril, 15 juillet et 15 octobre à minuit**, uniquement en production (fichier [app/app/schedule.py](../app/app/schedule.py)). Au moment de l'import, le système choisit automatiquement le millésime le plus récent parmi ceux déjà publiés.

**Point de vigilance.** La liste des millésimes est écrite en dur dans le code ([import_bdtopo.py](../app/batid/services/imports/import_bdtopo.py), fonction `_bdtopo_release_dates`) et s'arrête fin 2030. Il faudra la prolonger avant cette date, sinon l'import ne trouvera plus de millésime à utiliser.

## Process d'import

Tout le processus repose sur des tâches asynchrones (Celery) exécutées par les workers de l'application. Le code principal est dans [app/batid/services/imports/import_bdtopo.py](../app/batid/services/imports/import_bdtopo.py).

### 1. Déclenchement

La tâche `batid.tasks.queue_full_bdtopo_import` orchestre l'ensemble :

- elle établit la liste des départements à traiter : tous les départements français, sauf cinq territoires du Pacifique et des TAAF absents de la BD TOPO (Wallis-et-Futuna, Polynésie française, Nouvelle-Calédonie, TAAF, Clipperton) ;
- elle envoie une notification Mattermost annonçant le début de la campagne ;
- elle choisit le millésime à importer ;
- elle crée **une chaîne de tâches par département**, toutes reliées par un même identifiant de campagne (`bulk_launch_uuid`). Les départements sont traités en parallèle.

En production, ce déclenchement est automatique (voir le calendrier). Pour le lancer à la main, depuis un shell Django (`docker exec -it web python manage.py shell`) :

```python
from app.celery import app

# Campagne complète, millésime le plus récent
app.send_task("batid.tasks.queue_full_bdtopo_import")

# Ou en restreignant la plage de départements et/ou le millésime
app.send_task(
    "batid.tasks.queue_full_bdtopo_import",
    kwargs={"dpt_start": "01", "dpt_end": "10", "released_before": "2026-01-01"},
)
```

Pour un seul département :

```python
from batid.services.imports.import_bdtopo import create_bdtopo_dpt_import_tasks

create_bdtopo_dpt_import_tasks("33", "2025-09-15").apply_async()
```

> ⚠️ Ne pas utiliser `python manage.py import_france bdtopo` : cette commande appelle la fonction d'import avec de mauvais arguments et ne fonctionne pas pour la BD TOPO.

### 2. Téléchargement

Pour chaque département, la tâche `dl_source` télécharge l'archive depuis la Géoplateforme de l'IGN (`data.geopf.fr`). L'URL est construite à partir du département, du millésime et de la projection cartographique locale (Lambert 93 en métropole, projections spécifiques pour les Outre-mer). L'archive `.7z` est ensuite décompressée : elle contient un fichier GeoPackage (`.gpkg`), un format standard de données géographiques. En cas d'échec, la tâche réessaie automatiquement (5 tentatives).

### 3. Création des candidats

La tâche `convert_bdtopo` lit la couche `batiment` du fichier GeoPackage et parcourt les bâtiments un par un :

- les **constructions légères** (serres, abris… identifiées par l'IGN) sont ignorées : elles ne correspondent pas à la définition d'un bâtiment du RNB ;
- les bâtiments dont l'identifiant IGN (`cleabs`) est **déjà rattaché à un bâtiment du RNB** sont ignorés : ils ont déjà été traités lors d'un import précédent ;
- les autres deviennent des candidats : leur géométrie est aplatie en 2D, convertie en coordonnées GPS (WGS 84) et réparée si besoin. Chaque candidat garde la trace de sa source (`bdtopo`), de son identifiant IGN et du millésime.

Les candidats sont ensuite insérés en masse dans la table `batid_candidate`, et le compteur de candidats créés est enregistré dans une ligne de suivi (`BuildingImport`, une par département et par campagne, visible dans l'admin Django). Les fichiers téléchargés sont enfin supprimés.

À noter : la BD TOPO ne fournit **aucune adresse** au RNB. Les candidats sont créés sans adresse ; le lien bâtiment ↔ adresse vient d'autres imports (BAN/BAL).

### 4. Inspection des candidats

**Cette étape n'est pas automatique.** Une fois les candidats créés, il faut lancer l'inspection :

```bash
docker exec web python manage.py inspect_candidates
```

Cette commande envoie une tâche qui examine les candidats un par un jusqu'à épuisement. Pour aller plus vite, on peut lancer la commande plusieurs fois : les tâches travaillent en parallèle sans se marcher dessus (chaque candidat est verrouillé le temps de son examen).

La logique de décision est décrite dans la section suivante.

## Algo

L'inspection est réalisée par la classe `Inspector` ([app/batid/services/candidate.py](../app/batid/services/candidate.py)). Pour chaque candidat, elle déroule les étapes suivantes.

### Étape 1 : contrôles de validité

Le candidat est refusé d'office si :

- c'est une construction légère (refus `is_light`) ;
- sa surface est inférieure à 5 m² (refus `area_too_small`) ou supérieure à 500 000 m² (refus `area_too_large`) ;
- sa géométrie est invalide (refus `invalid_geometry`).

### Étape 2 : recherche des bâtiments voisins

L'inspecteur cherche tous les bâtiments du RNB **actifs et réels** (statut correspondant à un bâtiment existant) situés à **moins de 3 mètres** du candidat.

### Étape 3 : comparaison géométrique

Chaque voisin est comparé au candidat. Le résultat est l'un des trois cas suivants :

| Cas | Règle (deux polygones) |
|---|---|
| **Correspondance** (`match`) | la surface commune couvre **au moins 85 %** du candidat **et** au moins 85 % du bâtiment |
| **Pas de correspondance** (`no_match`) | la surface commune couvre **moins de 10 %** de chacun des deux : le voisin est ignoré |
| **Conflit** (`conflict`) | tous les cas intermédiaires : le recouvrement est trop important pour être ignoré, trop faible pour conclure à un même bâtiment |

Cas particuliers : deux points correspondent s'ils sont quasi confondus (tolérance d'environ 1 cm) ; un point face à un polygone est toujours considéré comme une correspondance (la présélection à 3 mètres suffit).

### Étape 4 : décision

- **Un conflit avec au moins un voisin** → refus (`ambiguous_overlap`). Le doute profite à la base : on ne crée ni ne modifie rien.
- **Aucune correspondance** → **création** d'un nouveau bâtiment dans le RNB, avec le statut « construit », l'identifiant IGN en identifiant externe, et l'utilisateur système « RNB » comme auteur.
- **Une seule correspondance** → **mise à jour** du bâtiment existant :
  - ajout de l'identifiant IGN (et du millésime) à ses identifiants externes s'il ne l'a pas déjà ;
  - remplacement de sa géométrie **uniquement** si le bâtiment RNB était un simple point et que le candidat apporte un vrai contour (polygone) ;
  - si rien ne change au final → refus `nothing_to_update`.
- **Plusieurs correspondances** → refus (`too_many_geomatches`) : impossible de savoir à quel bâtiment rattacher le candidat.

Chaque décision (création, mise à jour ou refus, avec sa raison) est enregistrée dans le candidat lui-même (champ `inspection_details`), ce qui permet les vérifications ci-dessous.

## Vérification

Après chaque campagne, la vérification combine trois approches complémentaires : des **comptages globaux** comparés aux campagnes précédentes, des **vérifications visuelles** sur des échantillons, et une **confrontation avec les contributions** des utilisateurs. Cette méthode est issue des vérifications menées sur les campagnes de janvier 2025 à mai 2026 (notes détaillées dans [check_bdtopo](check_bdtopo/)).

### 1. Comptages globaux

La commande de contrôle intégrée :

```bash
docker exec web python manage.py verify_inspection 2026-07-15
```

La date passée en argument est le point de départ de l'analyse (typiquement la date de lancement de la campagne). Le rapport comprend trois contrôles, sélectionnables avec `--checks` :

- `count_decisions` : nombre de créations, mises à jour et refus ;
- `count_refusals` : détail des refus par raison (`is_light`, `ambiguous_overlap`, `too_many_geomatches`, etc.) ;
- `real_updates` : vérifie que chaque « mise à jour » a réellement modifié le bâtiment, et liste les mises à jour fantômes.

Les mêmes chiffres peuvent être obtenus directement en SQL, ce qui permet de creuser :

```sql
-- Nombre de candidats inspectés depuis le début de la campagne
select count(*) from batid_candidate where inspected_at > '2026-07-15';

-- Répartition des décisions
select inspection_details#>'{decision}' as decision, count(*)
from batid_candidate
where inspected_at > '2026-07-15'
group by inspection_details#>'{decision}';

-- Répartition des refus par raison
select inspection_details#>'{reason}' as reason, count(*)
from batid_candidate
where inspection_details @> '{"decision": "refusal"}' and inspected_at > '2026-07-15'
group by inspection_details#>'{reason}';
```

**Comparer avec les campagnes précédentes.** C'est le principal détecteur d'anomalies : chaque campagne doit être rapprochée des ordres de grandeur des campagnes passées, et tout écart important doit être expliqué avant de valider l'import. Valeurs observées :

|  | Janvier 2025 | Novembre 2025 | Janvier 2026 | Mai 2026 |
| --- | --- | --- | --- | --- |
| Candidats inspectés | — | 3 756 914 | 3 813 398 | 5 722 263 |
| Créations | 207 623 | 287 913 | 472 888 | 60 991 |
| Mises à jour | 8 142 | 7 749 | 20 283 | 6 883 |
| Refus | 3 445 985 | 3 461 252 | 3 320 227 | 5 654 389 |
| dont `ambiguous_overlap` | 2 574 413 | — | 2 611 394 | 4 564 735 |
| dont `area_too_small` | 807 802 | — | 611 287 | 1 036 586 |
| dont `nothing_to_update` | 62 268 | — | 95 725 | 49 857 |
| dont `too_many_geomatches` | 1 062 | — | 1 821 | 3 211 |

Lecture de ces chiffres :

- l'immense majorité des candidats (≈ 90 %) est **refusée**, et c'est normal : la plupart des bâtiments BD TOPO recouvrent partiellement des bâtiments déjà présents dans le RNB (`ambiguous_overlap`, de loin la première raison de refus) ;
- viennent ensuite les surfaces trop petites (`area_too_small`), puis les bâtiments déjà à jour (`nothing_to_update`) ;
- les refus `is_light` et `topology_exception` doivent rester à zéro ou marginaux ;
- un écart fort par rapport à la campagne précédente est un signal d'alerte. Exemple réel (mai 2026) : beaucoup plus de candidats inspectés mais beaucoup moins de créations que d'habitude — ce genre d'écart doit être investigué (échantillon cartographique, répartition des refus) avant de conclure.

Mettre à jour ce tableau après chaque campagne.

### 2. Vérifications visuelles par échantillons

Les comptages ne disent pas si les bâtiments créés sont de *bons* bâtiments. On tire donc des échantillons qu'on passe en revue sur un fond de carte (photo aérienne, Street View, cadastre au besoin).

**a) Carte d'un échantillon aléatoire.** Afficher 10 000 candidats inspectés (ou 10 000 créations, ou 10 000 refus d'une raison donnée) sur une carte de France :

```sql
with subset_q as (
    select shape from batid_candidate
    where inspection_details @> '{"decision": "creation"}'
    and inspected_at > '2026-07-15'
    limit 10000
)
select ST_Collect(shape) from subset_q;
```

Ce qu'on vérifie : la **couverture géographique**. Les points doivent couvrir tout le territoire de façon à peu près homogène. Des zones vides ou des paquets concentrés sur certaines régions signalent des départements manquants ou un import partiel (comparer les cartes des campagnes passées dans [check_bdtopo](check_bdtopo/)).

**b) Revue individuelle d'un échantillon de créations** (une cinquantaine). Requête pour récupérer un échantillon avec le contexte (bâtiments RNB voisins) :

```sql
select c.source_id, b.rnb_id, c.shape as c_shape, b.shape as b_shape, c.inspection_details
from batid_candidate as c
left join batid_building as b on st_intersects(c.shape, b.shape)
where c.inspected_at > '2026-07-15'
and c.inspection_details @> '{"decision":"creation"}'
limit 15 offset 10000;
```

Pour chaque bâtiment créé, on regarde la photo aérienne et on note : 🟢 création légitime, 🟠 douteux, 🛑 erreur. Lors des campagnes passées, la grande majorité des créations était légitime ; les cas douteux récurrents sont décrits plus bas (« Défauts connus de la BD TOPO »).

**c) Contrôle des mises à jour.** Le contrôle `real_updates` de `verify_inspection` détecte les mises à jour fantômes ; compléter par une revue visuelle rapide de quelques mises à jour.

### 3. Confrontation avec les contributions

Le RNB reçoit des contributions directes d'utilisateurs, dont il faut vérifier qu'elles ne sont pas dégradées par l'import. Deux contrôles menés en octobre 2025 :

```sql
-- Mises à jour touchant des bâtiments créés par des contributeurs
select count(*)
from batid_candidate as c
inner join batid_building_history as hist on c.inspection_details ->> 'rnb_id' = hist.rnb_id
where c.inspected_at > '2026-07-15'
and c.inspection_details @> '{"decision":"update"}'
and hist.event_type = 'creation'
and hist.event_origin ->> 'source' = 'contribution';

-- Conflits (ambiguous_overlap) entre un candidat et un bâtiment contribué,
-- avec un recouvrement significatif (IoU > 0.2)
select c.source_id, bdg.rnb_id,
(st_area(st_intersection(bdg.shape, c.shape)) / st_area(st_union(bdg.shape, c.shape))) as IoU,
c.shape as c_shape, bdg.shape, c.inspection_details
from batid_candidate as c
inner join batid_building_history as bdg on bdg.shape && c.shape
where c.inspected_at > '2026-07-15'
and c.inspection_details @> '{"decision":"refusal", "reason":"ambiguous_overlap"}'
and bdg.event_type = 'creation'
and bdg.event_origin ->> 'source' = 'contribution'
and (st_area(st_intersection(bdg.shape, c.shape)) / st_area(st_union(bdg.shape, c.shape))) > 0.2
limit 35;
```

(L'« IoU » — intersection sur union — mesure le recouvrement entre les deux formes : 1 = identiques, 0 = disjointes.)

On passe ensuite ces conflits en revue visuellement pour juger, cas par cas, quelle forme est la plus fidèle à la réalité. Enseignement d'octobre 2025 : les contributions RNB soutiennent bien la comparaison. La BD TOPO semble plus précise pour les petits bâtiments isolés ; en revanche, elle a tendance à fusionner en un seul bâtiment de gros ensembles qui devraient rester découpés.

### Défauts connus de la BD TOPO

Les revues visuelles des campagnes passées font ressortir des défauts récurrents de la source, à connaître pour ne pas s'en étonner :

- **Morceaux de bâtiments** : quand un bâtiment RNB existant est mal calé sur la réalité, la BD TOPO apporte parfois un « bout » complémentaire qui passe les seuils de l'algorithme et crée un bâtiment supplémentaire, sans réellement améliorer le RNB. Ces morceaux devraient plutôt être fusionnés avec le bâtiment principal — c'est le cas douteux le plus fréquent parmi les créations.
- **Constructions légères non marquées** : certains abris ou structures ouvertes ne sont pas signalés comme « construction légère » par l'IGN et deviennent des bâtiments RNB alors qu'ils ne correspondent pas à la définition.
- **Bâtiments créés sans adresse** : conséquence directe du fait que la BD TOPO ne porte pas d'adresse.

### Vérification du lien inverse (identifiants RNB dans la BD TOPO)

La BD TOPO contient elle-même un champ `IDS_RNB` reliant chaque bâtiment IGN à des identifiants RNB. Ce lien, calculé côté IGN, mérite ses propres contrôles :

- **Créations suspectes** : repérer les candidats décidés « création » alors que leur bâtiment BD TOPO portait déjà un identifiant RNB. Sur les départements testés en 2025 (Calvados, Ille-et-Vilaine), on trouve une poignée de cas par département — souvent des bâtiments démolis/reconstruits, ou des erreurs d'appariement côté IGN.
- **Recouvrement des liens** : pour chaque bâtiment BD TOPO lié à des identifiants RNB, comparer sa géométrie à la fusion (`ST_Union`) des géométries RNB liées. Un taux de recouvrement inférieur à 0,2 dans un sens ou dans l'autre signale un lien suspect. Mesure de février 2025 : environ **4 % des liens** sont suspects (testé sur le Calvados), soit des erreurs d'appariement IGN, soit des formes IGN qui ont évolué en conservant leur lien vers un RNB devenu obsolète.

### Suivi de campagne

- **Admin Django** : chaque ligne `BuildingImport` (une par département) affiche le nombre de candidats créés et l'identifiant de campagne. Attention : pour la BD TOPO, les compteurs de bâtiments créés/mis à jour/refusés de cet écran restent à zéro (ils ne sont pas alimentés par ce pipeline) ; se fier au rapport `verify_inspection`.
- **KPI quotidiens** : le nombre de modifications de bâtiments issues de l'import BD TOPO est calculé chaque nuit (KPI `building_changes_import_bdtopo`) et consultable publiquement via l'API : `GET /api/alpha/buildings/change_stats?since=…&until=…`.
- **Notifications** : le début de campagne et toute erreur dans les tâches d'import sont notifiés sur Mattermost. Le détail de l'exécution des tâches est visible dans Flower.

### En cas d'anomalie massive : l'exemple de novembre 2025

Un incident réel illustre la marche à suivre. Pendant l'inspection de la campagne d'automne 2025, un déploiement a modifié le code de validation des surfaces : **125 000 bâtiments de moins de 5 m²** ont été créés avant que l'erreur ne soit repérée. Enseignements :

- **Ne pas déployer pendant une inspection en cours** : l'inspection tourne longtemps, et un changement de code en cours de route s'applique aux candidats restants.
- **Faire un snapshot de la base avant l'inspection** : il borne l'incident dans le temps et permet de mesurer précisément ce qui s'est passé après.
- **Réparer par data fix plutôt que par restauration** : restaurer le snapshot aurait effacé les contributions et inscriptions intervenues entre-temps. La réparation choisie — désactiver les bâtiments fautifs via une tâche dédiée (`batid.tasks.deactivate_small_buildings`, tracée par un objet `DataFix`) — préserve la promesse de pérennité des identifiants RNB, au prix de statistiques de création faussées.
- **Toujours tester le fix sur staging** (copie de production) en comparant les compteurs avant/après, avant de le lancer en production.

Requête de surveillance associée (doit rester vide) :

```sql
select count(*) from batid_building
where is_active
and st_area(shape, true) < 5
and ST_GeometryType(shape) != 'ST_Point';
```

### Points de vigilance connus

- Un bâtiment déjà rattaché à un identifiant IGN n'est **jamais réexaminé** lors des millésimes suivants, même si sa géométrie a changé dans la BD TOPO.
- Un département dont tous les bâtiments seraient filtrés (aucun candidat) fait planter la tâche d'import de ce département (liste vide non gérée).
- Les bâtiments illisibles dans le fichier IGN (dates invalides, erreurs inattendues) sont ignorés silencieusement, sans compteur.
