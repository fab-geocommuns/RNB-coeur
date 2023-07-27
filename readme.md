# Référentiel National des Bâtiments (RNB)

**Référencer l’intégralité des bâtiments du territoire français au sein d’un géocommun**

Ce repository contient le coeur du RNB:

- le modèle de données
- les outils d'import des bâtiments
- les API bâtiments 
- les API Autorisations du Droit des Sols (ADS)

## Installation

### Cloner le repository

```bash
git clone git@github.com:fab-geocommuns/RNB-coeur.git
```

### Renseigner les fichiers de configuration

Pour une installation locale de la version de développement, copiez, renommez et remplissez les fichiers de configurations suivants : 

NB : l'extension `.example` devient `.dev`

- .env.app.example -> .env.app.dev
- .env.db_auth.example -> .env.db_auth.dev
- .env.rnb.example -> .env.rnb.dev
- .env.worker.example -> .env.worker.dev

### Construire et démarrer les conteneurs

```bash
docker compose build
docker compose up -d
```

## Installer les données d'un départements

```bash
docker exec -ti web python manage.py import_dpt_bdgs [numero_departement]
```