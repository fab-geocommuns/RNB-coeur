import datetime
from typing import Protocol, Optional
from dataclasses import dataclass
from db import get_conn, dictfetchone


@dataclass
class Signal:
    id: int
    type: str
    building_id: int
    origin: str
    handled_at: Optional[datetime.datetime] = None
    handle_result: Optional[dict] = None
    created_at: Optional[datetime.datetime] = None
    creator_copy_id: Optional[int] = None
    creator_copy_fname: Optional[str] = None
    creator_copy_lname: Optional[str] = None
    creator_org_copy_id: Optional[int] = None
    creator_org_copy_name: Optional[str] = None


def fetch_signal(pk: int) -> Signal:
    q = "SELECT * FROM batid_signal WHERE id = %(pk)s"
    conn = get_conn()
    with conn.cursor() as cur:
        data = dictfetchone(cur, q, {"pk": pk})
        if data:
            return Signal(**data)

    return None
