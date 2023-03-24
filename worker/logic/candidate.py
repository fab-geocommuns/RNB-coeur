from dataclasses import dataclass, field
from typing import List
from shapely.geometry import MultiPolygon
from shapely import wkb
from datetime import datetime
from db import dbgeom_to_shapely

@dataclass
class Candidate:
    id: int
    shape: MultiPolygon
    source: str
    source_id: str
    address_keys: List[str]
    created_at: datetime
    inspected_at: datetime
    inspect_result: str


def row_to_candidate(row):

    return Candidate(
        id= row['id'],
        shape= dbgeom_to_shapely(row.get('shape', None)),
        source= row['source'],
        source_id= row['source_id'],
        address_keys= row['address_keys'],
        created_at= row.get('created_at', None),
        inspected_at= row.get('inspected_at', None),
        inspect_result= row.get('inspect_result', None)
    )




