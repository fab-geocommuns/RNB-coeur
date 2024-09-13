# Documentation

L'ensemble de la [documentation](https://rnb.beta.gouv.fr/doc) destinée aux utilisateurs du RNB est accessible sur notre site sous forme d'un Gitbook.
Ce readme est quant à lui destiné aux personnes amenées à contribuer au code du projet.


# RNB-coeur

RNB-coeur contient le backend du projet RNB.

Le code du [site internet du RNB](https://rnb.beta.gouv.fr/) est quant à lui publié dans [ce repo](https://github.com/fab-geocommuns/RNB-site).

RNB-coeur est la partie backoffice du projet RNB, codé en Python/Django. Il contient :

- le modèle de données (base PostgreSQL) et la logique métier
- les outils d'import des bâtiments
- les API bâtiments
- les API Autorisations du Droit des Sols (ADS)

## Installation en local

Pour contribuer à ce repo, il faut commencer par le faire tourner en local sur sa machine. Nous parlons ici de contribution au code du RNB, pas au contenu du référentiel. Il vous faudra :

### 1. Installer git et docker sur votre machine

### 2. Cloner le repo
`git clone git@github.com:fab-geocommuns/RNB-coeur.git`

### 3. Renseigner les fichiers de configuration

Copiez, renommez et remplissez les fichiers de configurations ci-dessous.

Le détail des paramètres à modifier est disponible dans chacun des fichiers d'exemple.

NB : l'extension .example devient .dev

* .env.app.example -> .env.app.dev
* .env.db_auth.example -> .env.db_auth.dev
* .env.nginx-encrypt.example -> .env.nginx-encrypt.dev
* .env.rnb.example -> .env.rnb.dev
* .env.s3_backup.example -> .env.s3_backup.dev
* .env.sentry.example -> .env.sentry.dev
* .env.worker.example -> .env.worker.dev

### 4. Construire et démarrer les conteneurs docker

```
docker compose build
docker compose up -d
```

Le serveur local est lancé à l'adresse http://localhost:8000

## Lancer les tests
```
docker exec -ti web python manage.py test
```

## Ajouter une dépendance python

Nous utilisons [Poetry](https://python-poetry.org/) pour gérer nos dépendances python.
Pour ajouter une dépendance au projet, il faut [installer](https://python-poetry.org/docs/#installation) Poetry sur son poste.

Puis executer la commande `poetry add nom_du_package`.

Cela va mettre à jour le fichier pyproject.toml qui liste les dépendances du projet, ainsi que le fichier poetry.lock.
pyproject.toml ne liste que nos dépendances directes, tandis que poetry.lock contient également toutes les dépendances de nos dépendances.
Il n'est pas recommandé d'éditer le fichier pyproject.toml à la main.

### Options supplémentaires

* spécifier une version du package : `poetry add celery="~5.4.0"`
* ajouter le package en dépendance de dev uniquement : `poetry add --group=dev notebook="~6.5.4"`

## Formattage du code

Le projet utilise [pre-commit](https://pre-commit.com/) pour garantir le bon formattage du code. La configuration se trouve [ici](https://github.com/fab-geocommuns/RNB-coeur/blob/main/.pre-commit-config.yaml).
[precommit-ci](https://pre-commit.ci/) tourne sur chaque PR et commit automatiquement les corrections de formattage en cas d'erreur.

Il est possible d'[installer](https://pre-commit.com/#install) pre-commit en local sur sa machine pour que les corrections soient faites avant même de créer la PR, lors de chaque commit fait en local.


## A propos du RNB

La mission du RNB est de référencer l’intégralité des bâtiments du territoire français au sein d’un géocommun

Il s'agit d'un projet porté et financé par :
- l'Institut national de l’information géographique et forestière (IGN)
- l'Agence de l'environnement et de la maîtrise de l'énergie (Ademe)
- le Centre scientifique et technique du bâtiment (CSTB)
- la Direction générale de l'aménagement, du logement et de la nature (DGALN)

Le projet est incubé au sein du programme beta.gouv.fr.

## License

Projet distribué sous la License Apache 2. Voir la [`LICENSE`](LICENSE) pour plus de détails.
