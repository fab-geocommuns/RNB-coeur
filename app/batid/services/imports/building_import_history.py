import uuid
from batid.models import BuildingImport


def insert_building_import(source, dpt) -> BuildingImport:
    building_import = BuildingImport.objects.create(
        import_source=source,
        bulk_launch_uuid=uuid.uuid4(),
        departement=dpt,
        candidate_created_count=0,
        building_created_count=0,
        building_updated_count=0,
        building_refused_count=0,
    )
    building_import.save()
    return building_import


def increment_created_candidates(building_import, candidates_count) -> BuildingImport:
    building_import.candidate_created_count += candidates_count
    building_import.save()
    return building_import
