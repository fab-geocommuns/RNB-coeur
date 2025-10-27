# Rapprochements

Nous appelons rapprochement le fait de relier un fichier/une base de données au RNB, ie attribuer à chaque entité (bâtiment, logement, objet, groupe de bâtiments) un ou plusieurs identifiant RNB.

Ici, l'objectif est d'effectuer des rapprochements à partir de l'accès à une base du RNB
Si ce n'est pas votre cas, vous pouvez vous référez à [la documentation pour effectuer des rapprochements via l'api](https://rnb-fr.gitbook.io/documentation/guides/faire-et-refaire-un-rapprochement-avec-le-rnb)


## 1. Configurer les accès à une base du RNB

Si vous souhaitez effectuer le rapprochement partir d'une copie de la base du RNB en local, dans ce cas, à partir d'un fichier de backup (via pg_dump), vous pouvez le restorer localement via pg_restore ou la commande psql adaptée.
Attention, la base est volumnineuse, assurez vous d'avoir l'espace disque nécéssaire.

Dans tous les cas, mettez à jour le fichier [`.env.db_auth.dev`](.env.db_auth.dev) avec les accès à la base de donnée concernée.

Attention, vos requêtes peuvent faire monter en charge la base de donnée.
Aussi, il peut être utile d'utiliser un profil d'accès en lecture seule.

## 2. Construire et démarrer les conteneurs docker

```
docker compose build
docker compose up -d web
```

## 3. Lancer un Jupyter Notebook
De nombreux rapprochements ont été effectués en utilisant des notebook jupyter.

A cette fin, executez la commande suivante pour lancer jupyter sur le service docker `web` (qui a de nombreuses dépendances installées pour le projet, ce qui vous facilitera la vie lors de vos rapprochements)

```
docker compose exec --user root web python manage.py shell_plus --notebook
```

Puis ouvrez dans votre navigateur web (ou votre éditeur de code) l'url qui s'affiche dans votre console, il devrait ressembler à :
`http://127.0.0.1:8888/?token=XXXX`

Ensuite, il ne vous reste qu'a vous inspirer [des notebook existants](app/notebooks/rapprochements) pour effectuer votre rapprochement !

## 4. vous pouvez également utiliser l'api en local

Par exemple
```
http://127.0.0.1:8000/api/alpha/buildings/CDVXSAKG94Q5/
```

Le reste de la documentation de l'api est [disponible en ligne](https://rnb-fr.gitbook.io/documentation/api-et-outils/api-batiments)
