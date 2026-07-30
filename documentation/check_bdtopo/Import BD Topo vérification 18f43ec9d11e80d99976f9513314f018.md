# Import BD Topo : vérification

[Vérification du lien RNB ↔ BD Topo](Import%20BD%20Topo%20v%C3%A9rification/V%C3%A9rification%20du%20lien%20RNB%20%E2%86%94%20BD%20Topo%201a043ec9d11e80aab57cce1ac5fa7ae4.md)

On cherche à vérifier que les créations et mises à jour de bâtiments sont de qualité. 

Pour chaque cas, on récupère des échantillons qu’on passe en revue visuellement.

```sql
-- Check inspected candidates after a date
@set date = '2025-01-31 00:00:00.000 +0200'
```

## Vue globale

```sql
-- Combien de candidats ont été inspectés ?
select count(*) from batid_candidate where inspected_at > ${date};

-- Répartition des décisions
select inspection_details#>'{decision}' as reason, count(*) from batid_candidate where inspected_at > ${date} group by inspection_details#>'{decision}';

-- ##################
-- Creations
select count(*) from batid_candidate where inspection_details @> '{"decision": "creation"}' and inspected_at > ${date};

-- Afficher sur une carte, un échantillon des créations
with subset_q as (
	select shape from batid_candidate where inspection_details @> '{"decision": "creation"}' and inspected_at > ${date} limit 10000
)
select ST_Collect(shape) from subset_q;

-- ##################
-- Update
select count(*) from batid_candidate where inspection_details @> '{"decision": "update"}' and inspected_at > ${date};

-- ##################
-- Refus

-- Compter tous les refus
select count(*) from batid_candidate where inspection_details @> '{"decision": "refusal"}' and inspected_at > ${date};

-- Refus pour une raison spécifique
select count(*) from batid_candidate c where inspection_details @> '{"decision": "refusal", "reason":"too_many_geomatches"}' and c.inspected_at > ${date};

-- Compter les refus par raisons
select inspection_details#>'{reason}' as reason, count(*) from batid_candidate where inspection_details @> '{"decision": "refusal"}' and inspected_at > ${date} group by inspection_details#>'{reason}';
```

|  | Janvier 2025 | Novembre 2025 PROD | Janvier 2026 PROD | Mai 2026 PROD |
| --- | --- | --- | --- | --- |
| Millésime BD Topo | 2024-12-15 | 2025-09-15 |  | 2026-03-15 |
| NB candidats inspectés |  | 3 756 914 | 3 813 398 | 5 722 263 |
| Nb création | 207 623 | 287 913 | 472 888 | 60 991 |
| Nb update | 8 142 | 7 749 | 20 283 | 6 883 |
| Nb refus | 3 445 985 | 3 461 252 | 3 320 227 | 5 654 389 |
| Refus : `too_many_geomatches` | 1062 |  | 1 821 | 3 211 |
| Refus : `ambiguous_overlap` | 2 574 413 |  | 2 611 394 | 4 564 735 |
| Refus : `area_too_small` | 807 802 |  | 611 287 | 1 036 586 |
| Refus : `is_light` | 0 |  |  |  |
| Refus : `topology_exception` | 0 |  |  |  |
| Refus : `nothing_to_update` | 62 268 |  | 95 725 | 49 857 |

[Détails import BD Topo janvier 2025](Import%20BD%20Topo%20v%C3%A9rification/D%C3%A9tails%20import%20BD%20Topo%20janvier%202025%2029443ec9d11e8008bb08c664158f405d.md)

[Détails import octobre 2025](Import%20BD%20Topo%20v%C3%A9rification/D%C3%A9tails%20import%20octobre%202025%2029543ec9d11e8004be71f1dcafea0ab1.md)

[Détails import mai 2026](Import%20BD%20Topo%20v%C3%A9rification/D%C3%A9tails%20import%20mai%202026%2035943ec9d11e803a81a7c906796c925d.md)