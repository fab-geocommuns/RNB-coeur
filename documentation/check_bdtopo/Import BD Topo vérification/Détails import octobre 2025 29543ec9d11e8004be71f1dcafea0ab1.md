# Détails import octobre 2025

<aside>
👋

**Conclusions**

- La BD Topo continue d’être une source de données essentielle au RNB, elle nous  permet de créer de nombreux bâtiments légitimes (environ 156000 créations cette fois).
- La BD Topo est imparfaite. Il y a des cas d’erreurs faciles à trouver (et donc probablement assez nombreux).
    - Elle introduit de nouveaux bâtiments ayant plutôt vocation à être fusionné avec des bâtiments existants (ou créé en même temps) (ex : XRS9772ZW4TM).
    - On trouve quelques cas de bâtiments ne correspondants pas à la définition (ex: 6VNNY1V8WNN4).
- 1383 bâtiments créés par des contributeurs ont été mis à jour avec un ID BD Topo.
- 221 candidats ont été refusés car il recouvraient de façon ambigu des bâtiments créés par des contributeurs. Les contributions RNB semblent soutenir la comparaison par rapport à la BD Topo. Cette dernière **semble** plus précise pour les petits bâtiments isolés. En revanche sur les gros bâtiments, la BD Topo **semble** sous-découper.
</aside>

<aside>
⚠️

L’inspection des candidats sur la prod a donné lieu à la création de 125 014 bâtiments de moins de 5 mètres carrés.
Le code responsable de cette erreur est celui de [cette PR](https://github.com/fab-geocommuns/RNB-coeur/pull/751). Le code a été déployé alors que l’inspection était quasi finie. Cela explique le faible nombre de bâtiments créés.
→ 

[Création de bâtiments trop petits pendant import BD Topo T4 2025](D%C3%A9tails%20import%20octobre%202025/Cr%C3%A9ation%20de%20b%C3%A2timents%20trop%20petits%20pendant%20import%20B%202a143ec9d11e807b9ca0dd9c8886812a.md)

</aside>

## **Creations**

```sql
select c.source_id, b.rnb_id,  c.shape as c_shape,  b.shape as b_shape, c.inspection_details  
from batid_candidate as c  
left join batid_building as b on st_intersects(c.shape, b.shape)
where c.inspected_at > '2025-10-21'
and c.inspection_details @> '{"decision":"creation"}'
limit 15 offset 10000; 
```

![XRS9772ZW4TM (en vert) créé. N’améliore pas le RNB (besoin d’une fusion)](D%C3%A9tails%20import%20octobre%202025/Capture_decran_2025-10-27_a_09.08.28.png)

XRS9772ZW4TM (en vert) créé. N’améliore pas le RNB (besoin d’une fusion)

- V28V6FKJ59WB 🟠 - dur à a dire si c’est vraiment un bâtiment. Vue aérienne flou, pas visible sur streetview
- 77Q6YGTGC8XF 🟢
- 6VNNY1V8WNN4 🟠
    
    ![ca semble être un bâtiment léger et ouvert. Id bd topo : BATIMENT0000002492564162](D%C3%A9tails%20import%20octobre%202025/Capture_decran_2025-10-27_a_09.36.25.png)
    
    ca semble être un bâtiment léger et ouvert. Id bd topo : BATIMENT0000002492564162
    
- SCKQXS76R27V 🟢
- QSYTNSAZ16AW 🟢
- H12M3KZMNY3Y 🟢
- VZ9SV7FBCXQ1 🟠 - très dur à dire. On voit un petit bout de tole en vue aérienne. Rien sur SV, rien sur le cadastre
- QAXX4P2EPZGB 🟢
- 4K27X9W3AY23 🟠 - morceau de maison existe mais dégrade le rnb : besoin d’une fusion + bâtiment sans adresse
    
    ![Capture d’écran 2025-10-27 à 09.58.28.png](D%C3%A9tails%20import%20octobre%202025/Capture_decran_2025-10-27_a_09.58.28.png)
    
- HNNKEYX5DA7R 🟢 (deuxième bout de 4K27X9W3AY23)
- 7AFD93K38MTQ 🟠 la forme semble mauvaise. j’ai plutot l’impression qu’il y a un petit batiment en fond de cours au sud.
    
    ![Capture d’écran 2025-10-27 à 10.17.49.png](D%C3%A9tails%20import%20octobre%202025/Capture_decran_2025-10-27_a_10.17.49.png)
    
- 9X8YBYSKYNP5 🟢
- HDZZASQG8NR9 🟢
- 8PYQ2H7YKZ9T 🟢
- F8XEY33DSKMM 🟢
- J66W7VWERQJM 🟢
- M72TZPSEQZ9Y 🟢
- VC8S7E95HN1A 🟢
- MAYGPMEV6Y13 🟠 - devrait être fusionné avec N9VN86F753ZK
- N9VN86F753ZK 🟢
- FC7BWDY3F657 🟢
- MWG3VWNQQXAP 🟠 - devrait être fusionné avec XAB8JVPYX6CR
- EHTKVFFF3HJS 🟠 - devrait être fusionné avec KKZQX78DEN88
- X4AWK1DH4VAT 🟠 - devrait peut être fusionné avec 2NBBMV7N9X5K

## Mises à jour

```sql
select c.source_id, b.rnb_id,  c.shape as c_shape,  b.shape as b_shape, c.inspection_details  
from batid_candidate as c  
left join batid_building as b on st_intersects(c.shape, b.shape)
where c.inspected_at > '2025-10-21'
and c.inspection_details @> '{"decision":"update"}'
limit 15; 
```

- C41DQRFCF85M 🟢
- TP5Z3KVEZTQ5 🟢

Ici, j’ai coupé court sur la vérification des simples update. Je me suis concentré sur la relation avec les contributions.

**Mises à jour sur bâtiments créés par contribution = 1383**

```sql
select count(*) 
from batid_candidate as c  
inner join batid_building_history as hist on c.inspection_details ->> 'rnb_id' = hist.rnb_id
where c.inspected_at > '2025-10-21'
and c.inspection_details @> '{"decision":"update"}'
and hist.event_type = 'creation'
and hist.event_origin ->> 'source' = 'contribution';
```

## Refus pour ambiguous_overlap sur des bâtiments créés par les contribteurs

Il y 221 “conflits” basés sur la requête ci-dessous

```sql
select c.source_id, bdg.rnb_id,
(st_area(st_intersection(bdg.shape, c.shape)) / st_area(st_union(bdg.shape, c.shape)) ) as IoU,
c.shape as c_shape, bdg.shape, c.inspection_details
from batid_candidate as c  
inner join batid_building_history as bdg on bdg.shape && c.shape
where c.inspected_at > '2025-10-21'
and c.inspection_details @> '{"decision":"refusal", "reason":"ambiguous_overlap"}'
and bdg.event_type = 'creation'
and bdg.event_origin ->> 'source' = 'contribution'
and (st_area(st_intersection(bdg.shape, c.shape)) / st_area(st_union(bdg.shape, c.shape)) ) > 0.2
limit 35;
```

| id rnb | forme la plus précise |  | IoU |
| --- | --- | --- | --- |
| W9MDZ5JFP9AK | IGN (marginal) | 🟠 | 0.77 |
| CHZSMWD9K626 | IGN (marginal) | 🟠 | 0.80 |
| 9A5VBM66CQG3 | RNB | 🟢 | 0.68 |
| 3TGB1WF1JYTB | IGN | 🛑 | 0.76 |
| [**WJN8VVZZGTAD**](https://rnb-sandbox.vercel.app/carte?q=WJN8VVZZGTAD) | RNB (ign dessine un gros bout inexistant) | 🟢 | 0.61 |
| 65WH6Y88E7GN | RNB (IGN fusionne des bâtiments qui ne devraient pas l’etre) | 🟢 | 0.34 |
| N5X8E8R2SRRA | ??? | 🟠 | 0.81 |
| 94J263N5474M | RNB (IGN fusionne des bâtiments qui ne devraient pas l’etre) | 🟢 | 0.47 |
| XNK8HVNQTG18 | IGN (le RNB est très bien calé sur le toit mais ce n’est pas une orthophto) | 🛑 | 0.62 |
| T7TJ34RF52J7 | RNB | 🟢 | 0.81 |
| 4TW7RS7AJC9X | IGN | 🛑 | 0.82 |
| CG8V41P168AE | IGN | 🛑 | 0.79 |
| 39MM87QVQPSY | RNB (le RNB est très bien calé sur le toit mais ce n’est pas une orthophto) | 🟢 | 0.44 |
| AH56FDNQ6GWY | IGN (pas évident a cause de la partie Sud Est) | 🟠 | 0.49 |
| EZM6QDNRN52K | IGN (RNB probablement surdécoupé) | 🛑 | 0.41 |
| SSJHQSR3GCRQ | ??? (voir si les logements ont un seul accès commun) | 🟠 | 0.44 |
| 8YSHGR7YVADX | RNB (IGN fusionne des batiments séparés) | 🟢 | 0.35 |
| 4VRQE44MD2PS | RNB (IGN fusionne des batiments séparés) | 🟢 | 0.22 |
| DRKFF53VWCN6 | RNB (IGN fusionne des batiments séparés) | 🟢 | 0.21 |