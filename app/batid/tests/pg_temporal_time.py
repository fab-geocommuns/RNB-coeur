"""Synchroniser l'horloge du trigger temporel PostgreSQL avec les tests (freezegun).

Le trigger ``versioning()`` (migration 0062) utilise ``CURRENT_TIMESTAMP`` pour
``sys_period``, sauf si la variable de session ``user_defined.system_time`` est
définie. Sans cela, les tests qui figent le temps en Python voient quand même des
dates réelles en base, ce qui rend les filtres par mois non déterministes.
"""
from __future__ import annotations

import datetime

from django.db import connection

_PG_TIME_FMT = "%Y-%m-%d %H:%M:%S.%f"


def set_pg_temporal_system_time(dt: datetime.datetime) -> None:
    """
    Input: datetime timezone-aware (UTC recommandé), aligné sur le @freeze_time du test.
    Expected: les INSERT/UPDATE sur ``batid_building`` utilisent cette heure pour ``sys_period``.
    """
    if dt.tzinfo is None:
        msg = "dt must be timezone-aware so PG and month_bounds stay consistent"
        raise ValueError(msg)
    with connection.cursor() as cursor:
        cursor.execute(
            "SET user_defined.system_time = %s",
            [dt.strftime(_PG_TIME_FMT)],
        )


def reset_pg_temporal_system_time() -> None:
    """Remet le comportement par défaut du trigger (horloge réelle)."""
    with connection.cursor() as cursor:
        cursor.execute("RESET user_defined.system_time")
