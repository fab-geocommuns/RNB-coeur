# Vérification du lien RNB ↔ BD Topo

On vérifie la qualité du lien RNB ↔ BD Topo mis à disposition par la BD Topo.

Pour cela : 

- on télécharge la BD Topo d’un département
- pour chaque bâtiment du fichier, on vérifie si il est attaché à au moins un ID RNB (champs `IDS_RNB`)
- On récupère les géométries des bâtiments RNB, on les fusionne (`ST_Union`) et on compare cette fusion avec la géomtrie de la BD Topo.
- Si un des taux de recouvrement (BD Topo sur RNB et RNB sur BD Topo) est inférieur à X, on considère le cas comme suspect.

Quand on compte les cas où on trouve un taux de recouvrement inférieur à 0.2, on trouve qu’environ 4% de la BD Topo Calvados (14) est concerné

## **Cas problématiques 21 février 2025**

**Cas 1**

![BD Topo (en bleu) lié à RNB (en rouge)](V%C3%A9rification%20du%20lien%20RNB%20%E2%86%94%20BD%20Topo/Capture_decran_2025-02-20_a_17.36.50.png)

BD Topo (en bleu) lié à RNB (en rouge)

![Nouveau bâtiment](V%C3%A9rification%20du%20lien%20RNB%20%E2%86%94%20BD%20Topo/Capture_decran_2025-02-20_a_17.37.49.png)

Nouveau bâtiment

![Vieux bâtiment démoli](V%C3%A9rification%20du%20lien%20RNB%20%E2%86%94%20BD%20Topo/Capture_decran_2025-02-20_a_17.41.44.png)

Vieux bâtiment démoli

```sql
RNB IDs : ['C13EXW9R248M'] - BD Topo ID : BATIMENT0000000000957871
BD TOPO area : 363.85356286354363 - rnb area 91.96297211945057 - Intersection area : 67.68428200483322
cover_ratio_bdtopo_on_rnb : 0.735994938451078 - cover_ratio_rnb_on_bdtopo : 0.18602066576497128
```

Le RNB (C13EXW9R248M) représente un vieux bâtiment démoli.

La BD (BATIMENT0000000000957871) Topo représente un nouveau bâtiment.

Ils sont liés dans la BD Topo alors qu’ils ne devraient pas l’être. 

**Le bâtiment BD Topo a la même forme depuis fin 2023. → problème d’appariement côté IGN**

**Le taux de couverture de la BD Topo par le RNB est très bas (18%)**

---

**Cas 2**

![BD Topo (orange) lié à RNB (bleu)](V%C3%A9rification%20du%20lien%20RNB%20%E2%86%94%20BD%20Topo/Capture_decran_2025-02-21_a_10.54.55.png)

BD Topo (orange) lié à RNB (bleu)

![Il s’agit de deux bâtiments](V%C3%A9rification%20du%20lien%20RNB%20%E2%86%94%20BD%20Topo/Capture_decran_2025-02-21_a_10.55.09.png)

Il s’agit de deux bâtiments

![Capture d’écran 2025-02-21 à 10.55.03.png](V%C3%A9rification%20du%20lien%20RNB%20%E2%86%94%20BD%20Topo/Capture_decran_2025-02-21_a_10.55.03.png)

```sql
RNB IDs : ['7MACMW3E898N'] - BD Topo ID : BATIMENT0000000013979976
BD TOPO area : 19.59749008936342 - rnb area 33.90835688915104 - Intersection area : 0.0036729813436977565
cover_ratio_bdtopo_on_rnb : 0.00010832082945525813 - cover_ratio_rnb_on_bdtopo : 0.0001874210078407579
```

La BD Topo représente le bâtiment de droite (orange) mais contient l’ID RNB du bâtiment de gauche.

**Les deux taux de couverture sont très bas (0.01%)**

---

**Cas 3**

![BD Topo (orange) RNB (bleu)](V%C3%A9rification%20du%20lien%20RNB%20%E2%86%94%20BD%20Topo/Capture_decran_2025-02-21_a_11.26.08.png)

BD Topo (orange) RNB (bleu)

![Le bâtiment RNB semble placé à un endroit sans réel bâtiment
La BD Topo a la bonne forme](V%C3%A9rification%20du%20lien%20RNB%20%E2%86%94%20BD%20Topo/Capture_decran_2025-02-21_a_11.27.48.png)

Le bâtiment RNB semble placé à un endroit sans réel bâtiment
La BD Topo a la bonne forme

![Le bâtiment BD Topo BATIMENT0000000013986702 en septembre 2023](V%C3%A9rification%20du%20lien%20RNB%20%E2%86%94%20BD%20Topo/Capture_decran_2025-02-21_a_11.33.20.png)

Le bâtiment BD Topo BATIMENT0000000013986702 en septembre 2023

```sql
RNB IDs : ['BSFXR6MHGT7F'] - BD Topo ID : BATIMENT0000000013986702
BD TOPO area : 20.278260773047805 - rnb area 23.611341710668057 - Intersection area : 0.0
cover_ratio_bdtopo_on_rnb : 0.0 - cover_ratio_rnb_on_bdtopo : 0.0
```

Le bâtiment RNB a été créé en décembre 2023 grâce à la BDNB

Toujours en décembre 2023, il a été associé par appariement géométrique au bâtiment BD Topo BATIMENT0000000013986702

Lors de l’import du RNB dans la BD Topo, le lien RNB ↔ BD Topo a été créé dans la BD Topo (sémantique ou géométrique ?)

L’enveloppe du bâtiment BD Topo a ensuite été modifiée et déplacée. Le lien avec le RNB a été conservé.

**Les deux taux de couverture sont nuls**

---

**Cas 4 (similaire au cas 3)**

![Capture d’écran 2025-02-21 à 11.41.36.png](V%C3%A9rification%20du%20lien%20RNB%20%E2%86%94%20BD%20Topo/Capture_decran_2025-02-21_a_11.41.36.png)

![Le bâtiment RNB a une forme qui ne correspond à rien.
La BD Topo a la bonne forme](V%C3%A9rification%20du%20lien%20RNB%20%E2%86%94%20BD%20Topo/Capture_decran_2025-02-21_a_11.42.19.png)

Le bâtiment RNB a une forme qui ne correspond à rien.
La BD Topo a la bonne forme

![Le bâtiment BD Topo BATIMENT0000000013991775 en septembre 2023](V%C3%A9rification%20du%20lien%20RNB%20%E2%86%94%20BD%20Topo/Capture_decran_2025-02-21_a_11.43.36.png)

Le bâtiment BD Topo BATIMENT0000000013991775 en septembre 2023

```sql
RNB IDs : ['K6DJMK36EHB3'] - BD Topo ID : BATIMENT0000000013991775
BD TOPO area : 170.566046372056 - rnb area 81.95484332181513 - Intersection area : 34.80041289329529
cover_ratio_bdtopo_on_rnb : 0.4246291187043481 - cover_ratio_rnb_on_bdtopo : 0.20402895906600946
```

Le cas est similaire au précédent. Le bâtiment BD Topo a été modifié.

---

**En résumé :** 

- Environ 4% (≈ 1,6M) des liens BD Topo ↔ RNB, présents dans la BD Topo ont un taux de couverture suspect. Il semble y avoir deux types de cas :
    - Cas 1 et 2 : l’appariement fait côté IGN devrait être plus conservateur → est-ce qu’il y a besoin de refaire tourner un appariement à chaque import du RNB dans la BD Topo ?
    - Cas 3 et 4 : quand une forme change côté IGN mais id est conservé → côté RNB, comment exploiter cette nouvelle forme ?