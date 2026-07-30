# Création de bâtiments trop petits pendant import BD Topo T4 2025

- 125k petits bâtiments
- le premier bâtiment inspecté de ce lot a été inspecté le 2025-11-01 13:34:18.424 +0100
- un snapshot de la base a été fait le 2 novembre 2025 à 14:12
- la [PR fautive](https://github.com/fab-geocommuns/RNB-coeur/pull/751) a été déployée le 3/11/2025
- le petit bâtiment le plus ancien a été créé le 2025-11-03 17:46:34.595 +0100

```sql
select * from batid_building 
where st_area(shape::geography)  <= 5 
and ST_GeometryType(shape) != 'ST_Point' 
and lower(sys_period) > '2025-10-30'
order by lower(sys_period) asc
limit 10
;
```

- le petit bâtiment le plus ancien a été créé le 2025-11-04 08:11:48.222 +0100

```sql
select * from batid_building 
where st_area(shape::geography)  <= 5 
and ST_GeometryType(shape) != 'ST_Point' 
and lower(sys_period) > '2025-10-30'
order by lower(sys_period) desc
limit 10
;
```

**Depuis le snapshot du 2 novembre 2025 à 14:12, il y a eu :** 

- 3653 contributions par 5 utilisateurs

```sql
-- nombre de contributions
select count(*) from batid_building_with_history where lower(sys_period) > '2025-11-02 14:12:00.000 +0100' and event_origin @> '{"source":"contribution"}';

-- nombre d'auteurs de ces contributions
select count(distinct event_user_id) from batid_building_with_history where lower(sys_period) > '2025-11-02 14:12:00.000 +0100' and event_origin @> '{"source":"contribution"}';
```

- 7 inscrits

```sql
select count(*) from auth_user where date_joined > '2025-11-02 14:12:00.000 +0100';
```

![Capture d’écran 2025-11-04 à 10.45.32.png](Cr%C3%A9ation%20de%20b%C3%A2timents%20trop%20petits%20pendant%20import%20B/Capture_decran_2025-11-04_a_10.45.32.png)

L’utilisation du snapshot ferait perdre un peu trop de matière (contrib + user) pour réparer un trop plein de bâtiments peu problématique.

**Possibilités de fix**

- ✅ data_fix → on désactive les bâtiments actifs faisant moins de 5m2
    - avantage : on conserve la promesse de pérennité des identifiants
    - désavantage : on fausse les stats de création de bâtiments
- suppression pure et simple → on recherche tous les bâtiments de moins de 5m2 créés depuis le 2025-11-03 17:46:34.595 +0100
    - avantage : base “propre”
    - désavantage : pas de pérennité des identifiants

**Vérification du bon fonctionnement du data_fix sur staging**

|  | Avant fix | Après fix |
| --- | --- | --- |
| Batiment actifs | 44056740 | 44056725 (-15) ✅ |
| Batiments inactifs | 4 690 879 | 4 690 894 (+15) ✅ |
| Batiment moins de 5m2, actif, avec polygon ou multiplolygon | 15 | 0 ✅ |

```sql
select count(*) from batid_building group by is_active;

select count(*) from batid_building 
where is_active
and st_area(shape, true) < 5
and ST_GeometryType(shape) != 'ST_Point';
```

```sql
>>> from batid.models.others import DataFix
>>> from django.contrib.auth.models import User
>>> u = User.objects.get(username="paul")
>>> df = DataFix.objects.create(user=u, text="d2sactivatin des petits batiments importés via la bd topo")
```

```sql
docker exec -ti web celery -A app call batid.tasks.deactivate_small_buildings --kwargs='{"fix_id":XXX, "batch_size":10000}'
```

**Sur staging de copie de prod**

|  | Avant fix | Après fix |
| --- | --- | --- |
| Batiment actifs | 44 374 429 | 44248381 (-126 048) ✅ |
| Batiments inactifs | 4 704 503 | 4830551 (- 126 048) ✅ |
| Batiment moins de 5m2, actif, avec polygon ou multiplolygon | 126 048 | 0 ✅ |