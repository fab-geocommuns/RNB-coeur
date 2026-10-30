import uuid

from batid.models import BuildingImport
from django.db import connection, transaction


def insert_building_import(source, bulk_launch_uuid, dpt) -> BuildingImport:
    if bulk_launch_uuid is None:
        return _create_building_import(
            source=source, bulk_launch_uuid=uuid.uuid4(), dpt=dpt
        )

    # A task replayed by Celery (acks_late, autoretry) reuses the row of its first run
    with transaction.atomic():
        lock_building_import(source=source, bulk_launch_uuid=bulk_launch_uuid, dpt=dpt)
        existing = (
            BuildingImport.objects.filter(
                import_source=source,
                bulk_launch_uuid=bulk_launch_uuid,
                departement=dpt,
            )
            .order_by("id")
            .first()
        )
        if existing is not None:
            return existing
        return _create_building_import(
            source=source, bulk_launch_uuid=bulk_launch_uuid, dpt=dpt
        )


def lock_building_import(*, source: str, bulk_launch_uuid, dpt: str | None) -> None:
    """Serialize, until the end of the current transaction, the runs of an import of
    a department within a bulk launch."""
    with connection.cursor() as cursor:
        # The worker statement_timeout would cancel the wait for a COPY of hours
        cursor.execute("SET LOCAL statement_timeout = 0")
        cursor.execute(
            "SELECT pg_advisory_xact_lock(hashtext(%s))",
            [f"building_import:{source}:{bulk_launch_uuid}:{dpt}"],
        )


def _create_building_import(*, source, bulk_launch_uuid, dpt) -> BuildingImport:
    return BuildingImport.objects.create(
        import_source=source,
        bulk_launch_uuid=bulk_launch_uuid,
        departement=dpt,
        candidate_created_count=0,
        building_created_count=0,
        building_updated_count=0,
        building_refused_count=0,
    )


def increment_created_candidates(building_import, candidates_count) -> BuildingImport:
    building_import.candidate_created_count += candidates_count
    building_import.save()
    return building_import
