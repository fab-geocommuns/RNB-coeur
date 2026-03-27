# Spec: Leaderboard mensuel par email
[PR 858](https://github.com/fab-geocommuns/RNB-coeur/pull/858)

## Objectif

Le 1er de chaque mois, envoyer un email récapitulatif à toutes les personnes qui ont :
- contribué au RNB (au moins une édition) le mois précédent, **ou**
- créé un compte le mois précédent.

L'email contient un classement de tous les contributeurs du mois avec leur nombre d'éditions.

---

## Définitions

### Qu'est-ce qu'une « édition » ?

Un `event_id` distinct sur le modèle `BuildingWithHistory` (vue PostgreSQL `batid_building_with_history`, qui réunit les bâtiments courants et leur historique).

Un seul event peut modifier plusieurs bâtiments ; il compte pour **1 édition**, quel que soit le nombre de bâtiments touchés.

Tous les `event_type` sont inclus : `creation`, `update`, `deactivation`, `reactivation`, `merge`, `split`, et leurs variantes `revert_*`.

### Qui sont les destinataires ?

L'union des deux groupes suivants, filtrés sur le mois précédent :

1. **Éditeurs** : utilisateurs avec au moins une édition dans le mois (champ `event_user` du modèle `BuildingWithHistory`)
2. **Nouveaux comptes** : utilisateurs dont le champ `date_joined` tombe dans le mois

Conditions de filtrage :
- L'utilisateur doit avoir un email non vide
- Les comptes staff (`is_staff=True`) sont exclus

---

## Requête ORM

### Classement des éditeurs du mois

**Fichier :** `batid/services/leaderboard.py`

```python
from django.db.models import Count
from batid.models.building import BuildingWithHistory


def get_monthly_edit_leaderboard(year: int, month: int) -> list[dict]:
    """
    Input: year and month (e.g. 2026, 2 for February 2026)
    Returns: list of dicts sorted by edit_count desc, e.g.:
        [{"event_user__username": "alice", "event_user__email": "alice@example.com", "edit_count": 42}, ...]
    A single event_id touching N buildings counts as 1 edit.
    Excludes rows with no event_user.
    """
    start, end = _month_bounds(year, month)
    return list(
        BuildingWithHistory.objects
        .filter(event_user__isnull=False)
        .extra(
            where=["lower(sys_period) >= %s AND lower(sys_period) < %s"],
            params=[start, end],
        )
        .values("event_user__username", "event_user__email")
        .annotate(edit_count=Count("event_id", distinct=True))
        .order_by("-edit_count")
    )
```

Note : `lower(sys_period)` est l'horodatage de début de la période de validité du bâtiment, c'est-à-dire le moment où l'événement a eu lieu. Le même pattern est utilisé dans `api_alpha/endpoints/buildings/get_diff.py`.

### Nouveaux utilisateurs du mois

```python
from django.contrib.auth.models import User


def get_monthly_new_users(year: int, month: int):
    """
    Input: year and month
    Returns: User queryset of non-staff users who joined in the given month and have an email.
    """
    start, end = _month_bounds(year, month)
    return User.objects.filter(
        date_joined__gte=start,
        date_joined__lt=end,
        is_staff=False,
    ).exclude(email="")


def _month_bounds(year: int, month: int) -> tuple:
    import datetime
    start = datetime.datetime(year, month, 1, tzinfo=datetime.timezone.utc)
    if month == 12:
        end = datetime.datetime(year + 1, 1, 1, tzinfo=datetime.timezone.utc)
    else:
        end = datetime.datetime(year, month + 1, 1, tzinfo=datetime.timezone.utc)
    return start, end
```

---

## Format de l'email

**Sujet :** `Contributions RNB – [mois année]` (ex : `Contributions RNB – février 2026`)

**Corps (HTML, en français) :**

```
Bonjour,

Voici le résumé des contributions au Référentiel National des Bâtiments pour le mois de février 2026 :

• alice – 42 éditions
• bob – 17 éditions
• carol – 3 éditions

Merci pour vos contributions !

L'équipe RNB
```

Si le classement est vide (aucune édition ce mois), l'email n'est pas envoyé.

---

## Mécanisme d'envoi

### Fonction de construction de l'email

**Fichier :** `batid/services/email.py`

```python
def build_monthly_leaderboard_email(
    leaderboard: list[dict],
    month_label: str,
    email: str,
) -> EmailMultiAlternatives:
    """
    Input:
        leaderboard: [{"event_user__username": str, "edit_count": int}, ...]
        month_label: human-readable month, e.g. "février 2026"
        email: recipient address
    Returns: EmailMultiAlternatives ready to send
    """
```

Template : `batid/templates/emails/monthly_leaderboard.html`

Expéditeur : `get_rnb_email_sender()` (suit le pattern existant)

### Tâche Celery

**Fichier :** `batid/tasks.py`

```python
@notify_if_error
@shared_task(autoretry_for=(Exception,), retry_kwargs={"max_retries": 3})
def send_monthly_leaderboard_emails():
    """
    Calcule le classement du mois précédent et envoie un email à chaque destinataire éligible.
    Ne fait rien si le classement est vide.
    """
```

Logique interne :
1. Calculer `(year, month)` du mois précédent à partir de `datetime.date.today()`
2. Appeler `get_monthly_edit_leaderboard(year, month)`
3. Si vide → return (rien à envoyer)
4. Construire la liste des destinataires :
   - emails des éditeurs du leaderboard (non vide, non staff)
   - emails des nouveaux utilisateurs du mois (`get_monthly_new_users`)
   - dédupliquer
5. Pour chaque destinataire, construire et envoyer l'email

### Planification

**Fichier :** `app/schedule.py` — ajout dans `common_schedule`

```python
"send_monthly_leaderboard_emails": {
    "task": "batid.tasks.send_monthly_leaderboard_emails",
    # 1er de chaque mois à 6h UTC
    "schedule": crontab(hour=6, minute=0, day_of_month=1),
},
```

---

## Tests

**Fichier :** `batid/tests/test_leaderboard.py`

### 1. `test_leaderboard_counts_distinct_events`
- **Input :** user A effectue 3 modifications de bâtiments via 2 `event_id` distincts en janvier ; user B effectue 1 modification via 1 `event_id` en janvier
- **Expected :** `[{username: A, edit_count: 2}, {username: B, edit_count: 1}]`

### 2. `test_leaderboard_excludes_other_months`
- **Input :** 1 événement en janvier, 1 événement en février
- **Expected :** requête sur janvier → 1 résultat ; requête sur février → 1 résultat différent

### 3. `test_leaderboard_excludes_null_event_user`
- **Input :** 1 bâtiment avec `event_user=None`
- **Expected :** classement vide

### 4. `test_get_monthly_new_users`
- **Input :** user A rejoint en janvier, user B rejoint en février
- **Expected :** requête sur janvier → seulement user A

### 5. `test_build_monthly_leaderboard_email`
- **Input :** leaderboard `[{"event_user__username": "alice", "edit_count": 5}]`, email destinataire
- **Expected :** instance `EmailMultiAlternatives`, le HTML contient "alice" et "5"

---

## Fichiers à créer / modifier

| Fichier | Action |
|---------|--------|
| `batid/services/leaderboard.py` | Créer – fonctions de requête |
| `batid/services/email.py` | Modifier – ajouter `build_monthly_leaderboard_email` |
| `batid/templates/emails/monthly_leaderboard.html` | Créer – template email |
| `batid/tasks.py` | Modifier – ajouter `send_monthly_leaderboard_emails` |
| `app/schedule.py` | Modifier – ajouter l'entrée de planification |
| `batid/tests/test_leaderboard.py` | Créer – tests |

---

## Vérification

```bash
# Tests unitaires
docker exec web python manage.py test batid.tests.test_leaderboard

# Déclenchement manuel
docker exec web python manage.py shell -c "
from batid.tasks import send_monthly_leaderboard_emails
send_monthly_leaderboard_emails.apply()
"
```
