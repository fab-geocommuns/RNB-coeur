from django.db import transaction
from django.db.models import QuerySet

from batid.models import BuildingHistoryOnly


def _fetch(batch_size: int) -> QuerySet[BuildingHistoryOnly]:

    q = """
        select * from batid_building_history
        where event_type is null and ((created_at::timestamp - lower(sys_period)::timestamp) < interval '2 second')
        limit %(batch_size)s
        for update skip locked
        ;
        """

    return BuildingHistoryOnly.objects.raw(
        q,
        {"batch_size": batch_size},
    )


def fill_empty_event_type(batch_size: int = 50_000) -> int:
    updated_rows = 0

    with transaction.atomic():

        rows = _fetch(batch_size)

        for row in rows:

            print(f"Processing row: {row.rnb_id}")
            print(row.created_at, row.sys_period.lower)

            if not isinstance(row, BuildingHistoryOnly):

                raise TypeError(
                    f"Expected BuildingHistoryOnly instance got {type(row)}"
                )

        updated_rows += BuildingHistoryOnly.objects.bulk_update(rows, ["event_type"])

    return updated_rows
