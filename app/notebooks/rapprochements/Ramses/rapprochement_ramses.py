"""
Rapprochement RAMSES (établissements scolaires) <-> RNB
=======================================================

Ce script rapproche le fichier des adresses et de la géolocalisation des
établissements du premier et second degré, publié par le ministère de
l'Éducation nationale, avec les bâtiments du Référentiel National des
Bâtiments (RNB).

Pour chaque établissement, il tente d'identifier le ou les identifiants RNB
(`rnb_id`) du ou des bâtiments correspondants.

Données en entrée
-----------------
Fichier CSV « Adresse et géolocalisation des établissements premier et second
degré » (open data Éducation nationale), séparateur « ; ».
Colonnes utilisées :
  - numero_uai                 : identifiant unique de l'établissement (UAI)
  - appellation_officielle     : nom officiel de l'établissement
  - adresse_uai                : libellé de voie de l'établissement
  - localite_acheminement_uai  : commune de l'établissement
  - latitude / longitude       : coordonnées géographiques (WGS84)

Méthode de rapprochement
------------------------
Le rapprochement s'appuie sur le moteur de rapprochement du RNB (classe
`Guesser`), qui applique successivement plusieurs stratégies (« handlers ») :

  1. GeocodeNameHandler   : géocodage par le nom de l'établissement, via un
                            serveur Photon, en restreignant la recherche à une
                            zone autour des coordonnées fournies.
  2. GeocodeAddressHandler : géocodage de l'adresse postale, puis recherche du
                            bâtiment RNB le plus proche du point géocodé.

Chaque établissement est marqué comme rapproché (« match ») dès qu'une
stratégie aboutit. Le résultat associe à chaque `numero_uai` la liste des
`rnb_id` trouvés ainsi que la raison du rapprochement (`match_reason`).

Résultat
--------
Un fichier CSV `Ramses_out_2.csv` associant chaque `ext_id` (le `numero_uai`)
aux `rnb_ids` rapprochés et à la raison du rapprochement.
Le script shell `merge_results.sh` permet ensuite de joindre ce résultat au
fichier source complet.

Pré-requis d'exécution
----------------------
Ce script s'exécute dans l'environnement du projet RNB (Django + base de
données du RNB + service de rapprochement `batid.services.guess_bdg_new`).
Un serveur de géocodage Photon doit être accessible (voir `photon_url`).

Exécution :
    python manage.py shell < rapprochement_ramses.py
ou cellule par cellule dans un notebook Jupyter configuré pour Django.
"""

import os

import pandas as pd

# Autorise l'exécution des requêtes ORM Django depuis un contexte asynchrone
# (nécessaire dans un notebook / shell interactif).
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"

# Affichage complet des DataFrames lors d'une exécution interactive.
pd.set_option("display.max_columns", None)
pd.set_option("display.max_rows", None)

# Chemins des fichiers (à adapter le cas échéant).
SOURCE_CSV = (
    "/app/notebooks/rapprochements/Ramses/"
    "fr-en-adresse-et-geolocalisation-etablissements-premier-et-second-degre.csv"
)
WORK_FILE = "./guesses_v6.json"  # Fichier de travail intermédiaire (reprenable).
OUTPUT_CSV = "/app/notebooks/rapprochements/Ramses/Ramses_out_2.csv"


# ---------------------------------------------------------------------------
# 1. Chargement des données source
# ---------------------------------------------------------------------------

# Le séparateur du fichier open data est « ; ».
# `adresse_uai` est forcé en chaîne pour préserver les éventuels zéros initiaux.
df = pd.read_csv(SOURCE_CSV, sep=";", dtype={"adresse_uai": "string"})

print("Nombre d'établissements dans le fichier source :", len(df))
print("Colonnes disponibles :", list(df.columns))


# ---------------------------------------------------------------------------
# 2. Transformation des lignes en entrées pour le moteur de rapprochement
# ---------------------------------------------------------------------------


def row_to_input(df_row_raw):
    """Convertit une ligne du fichier RAMSES en entrée pour le `Guesser`.

    Entrée : une ligne du DataFrame source (un établissement).
    Sortie : un dictionnaire normalisé avec identifiant, nom, adresse et
             coordonnées.

    L'adresse n'est conservée que si elle est exploitable, c'est-à-dire
    lorsqu'elle commence par un numéro de voie ; sinon elle est mise à None
    pour éviter un géocodage peu fiable.
    """
    df_row = dict(df_row_raw)

    lat = df_row["latitude"]
    lng = df_row["longitude"]

    if pd.isna(df_row["adresse_uai"]):
        address = None
    else:
        address = f"{df_row['adresse_uai']}, {df_row['localite_acheminement_uai']}"
        address = address.strip()
        # On n'exploite l'adresse que si elle débute par un numéro de voie.
        if not address[0].isdigit():
            address = None

    return {
        "ext_id": df_row["numero_uai"],
        "name": df_row["appellation_officielle"],
        "address": address,
        "lat": float(lat),
        "lng": float(lng),
    }


inputs = list(df.apply(row_to_input, axis=1))

print("Nombre d'entrées à rapprocher :", len(inputs))
print("Exemple d'entrée :", inputs[0])


# ---------------------------------------------------------------------------
# 3. Rapprochement avec le RNB
# ---------------------------------------------------------------------------

from batid.services.guess_bdg_new import (  # noqa: E402  (import après bootstrap Django)
    GeocodeAddressHandler,
    GeocodeNameHandler,
    Guesser,
)

# Le moteur traite les entrées par lots (`batch_size`) et sauvegarde l'état
# d'avancement dans le fichier de travail, ce qui permet de reprendre un
# traitement interrompu.
guesser = Guesser(batch_size=1000)

# Ordre des stratégies de rapprochement appliquées à chaque établissement :
guesser.handlers = [
    # 3a. Géocodage par le nom de l'établissement via Photon, recherche
    #     limitée à un carré d'environ 1 km de demi-côté autour des
    #     coordonnées fournies.
    GeocodeNameHandler(
        sleep_time=0,
        photon_url="http://host.docker.internal:2322/api/",
        bbox_apothem_in_meters=1000,
    ),
    # 3b. Géocodage de l'adresse postale puis recherche du bâtiment RNB le plus
    #     proche dans un rayon de 200 m.
    GeocodeAddressHandler(closest_radius=200),
]

# Création du fichier de travail puis exécution du rapprochement.
guesser.create_work_file(list(inputs), WORK_FILE)
guesser.guess_work_file(WORK_FILE)


# ---------------------------------------------------------------------------
# 4. Bilan du rapprochement
# ---------------------------------------------------------------------------

# Rechargement du fichier de travail et affichage des statistiques
# (taux de rapprochement, détail par stratégie).
guesser = Guesser()
guesser.load_work_file(WORK_FILE)
guesser.report()


# ---------------------------------------------------------------------------
# 5. Export du résultat
# ---------------------------------------------------------------------------

# Export CSV : une ligne par établissement, avec la colonne d'identifiant
# nommée d'après le `numero_uai` (ext_id).
guesser.to_csv(OUTPUT_CSV, ext_id_col_name="ext_id")
