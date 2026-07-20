# RNB — Référentiel National des Bâtiments

Registre national attribuant un identifiant pérenne (`rnb_id`) à chaque bâtiment du territoire français, et exposant une API de consultation et de contribution.

## Language

**Bâtiment réel** :
Bâtiment dont l'existence physique est avérée — statut `constructed` ou `notUsable`. Un bâtiment démoli n'est pas réel.
_Avoid_ : bâtiment existant, bâtiment valide

**Bâtiment actif** :
Bâtiment faisant partie de la version courante du RNB (`is_active`). La désactivation est un événement de cycle de vie du registre, pas un fait physique : un bâtiment désactivé n'est pas un bâtiment démoli.
_Avoid_ : bâtiment vivant, bâtiment courant

**Emprise** :
Géométrie surfacique (polygone ou multipolygone) au sol d'un bâtiment. Certains bâtiments n'ont pas d'emprise connue : leur géométrie se réduit à un point. Les métriques surfaciques (IoU, taux de couverture) sont alors indéfinies (`null`), jamais 0 — 0 signifie « aucun recouvrement », `null` signifie « recouvrement inconnu ».
_Avoid_ : forme, géométrie (trop générique), footprint

**IoU (Intersection over Union)** :
Mesure de similarité entre deux emprises : aire de l'intersection divisée par l'aire de l'union, entre 0 (disjoints) et 1 (identiques). Symétrique.
_Avoid_ : taux de recouvrement (directionnel, voir taux de couverture), score de similarité

**Taux de couverture** :
Part d'une emprise couverte par une autre : aire(∩) / aire(emprise couverte). Directionnel — toujours nommer qui couvre qui, sur le modèle `X_covered_by_Y` (ex. `input_covered_by_rnb` : part du polygone fourni couverte par le bâtiment RNB ; `rnb_covered_by_input` : l'inverse).
_Avoid_ : pourcentage d'inclusion, ratio (sans direction)

**Rapprochement** :
Démarche d'un réutilisateur cherchant les identifiants RNB correspondant à ses propres géométries. Le RNB fournit des candidats et des métriques ; la décision d'appariement appartient au réutilisateur.
_Avoid_ : matching, appariement automatique
