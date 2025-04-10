from typing import Optional
from datetime import date

from batid.models import KPI


def get_kpi(
    name: str, since: Optional[date] = None, until: Optional[date] = None
):

    qs = KPI.objects.filter(name=name)
    if since:
        qs = qs.filter(value_date__gte=since)
    if until:
        qs = qs.filter(value_date__lte=until)

    return qs


def get_kpi_most_recent(name: str):

    return KPI.objects.filter(name=name).last()
