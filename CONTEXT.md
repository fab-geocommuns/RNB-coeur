# CONTEXT — Glossaire du RNB

Vocabulaire canonique du projet. Un terme = une définition. Pas de détails d'implémentation.

## Bâtiment (Building)

L'entité centrale du RNB. Identifiée par un `rnb_id`. Un bâtiment n'est **jamais supprimé** :
il est au plus *désactivé* (voir Désactivation).

## Fonction métier

Une opération sanctionnée de modification du référentiel : création, mise à jour,
désactivation, réactivation, fusion, division, et leurs annulations (reverts).
Chaque fonction métier garantit le bon remplissage du référentiel : identifiant d'événement,
type d'événement, utilisateur à l'origine, historique. **C'est la seule voie légitime
d'écriture d'un bâtiment.**

## Fonction native Django

Les mécanismes d'écriture génériques fournis par Django (sauvegarde et suppression directes,
opérations d'écriture en masse). Utilisées sur un bâtiment, elles contournent les garanties
des fonctions métier et compromettent le remplissage du référentiel. Elles sont **interdites
sur le modèle Building** — sauf dans les tests, et en interne au sein des fonctions métier
elles-mêmes.

## Désactivation

Marquer un `rnb_id` comme inactif parce qu'il n'aurait jamais dû entrer dans le RNB
(ex. : des arbres pris pour un bâtiment). À ne pas confondre avec une **démolition**,
qui est un changement de *statut* du bâtiment (une mise à jour) : le bâtiment démoli
reste un bâtiment légitime du référentiel.

## Événement

Toute modification du référentiel est un événement (`event_id`), d'un type donné
(création, mise à jour, désactivation, réactivation, fusion, division, revert…).
Un événement peut toucher plusieurs bâtiments à la fois (fusion, division) ; tous
partagent alors le même `event_id`.

## Écriture « forever »

Toute écriture d'un bâtiment entre définitivement dans l'historique du référentiel
(versionnage temporel). Rien n'est jamais effacé : l'auditabilité complète de
l'historique est une propriété fondatrice du RNB.

## Historique

Les versions passées des bâtiments. Consultable, jamais modifiable par le code
applicatif : seul le mécanisme de versionnage l'alimente.
