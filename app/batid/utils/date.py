import datetime

from django.utils import translation
from django.utils.dates import MONTHS


def month_bounds(year: int, month: int) -> tuple:
    start = datetime.datetime(year, month, 1, tzinfo=datetime.timezone.utc)
    if month == 12:
        end = datetime.datetime(year + 1, 1, 1, tzinfo=datetime.timezone.utc)
    else:
        end = datetime.datetime(year, month + 1, 1, tzinfo=datetime.timezone.utc)
    return start, end


def french_month_year_label(year: int, month: int) -> str:
    with translation.override("fr"):
        return f"{MONTHS[month]} {year}"


def iso_to_french_date(iso_date: str) -> str:
    return datetime.date.fromisoformat(iso_date).strftime("%d/%m/%Y")


def previous_month() -> tuple[int, int]:
    today = datetime.date.today()
    if today.month == 1:
        return today.year - 1, 12
    return today.year, today.month - 1
