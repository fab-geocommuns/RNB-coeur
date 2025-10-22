# app/dbrouters.py
import threading
from contextlib import contextmanager

from batid.models import BuildingAddressesReadOnly
from batid.models import BuildingHistoryOnly
from batid.models import BuildingWithHistory


class ModelReadOnlyError(Exception):
    def __init__(self, model: str):
        super().__init__(f"{model} model is read only!")


class DBRouter(object):
    # Thread-local storage to track when dangerous writes are allowed
    _local = threading.local()

    def db_for_write(self, model, **hints) -> str | None:
        allow_building_history_writes = getattr(
            self._local, "allow_building_history_writes", False
        )

        if model == BuildingHistoryOnly and not allow_building_history_writes:
            raise ModelReadOnlyError("BuildingHistoryOnly")
        if model == BuildingWithHistory:
            raise ModelReadOnlyError("BuildingWithHistory")
        if model == BuildingAddressesReadOnly:
            raise ModelReadOnlyError("BuildingAddressesReadOnly")
        return None

    @staticmethod
    @contextmanager
    def dangerously_allow_write_to_building_history():
        DBRouter._local.allow_building_history_writes = True
        try:
            yield
        finally:
            DBRouter._local.allow_building_history_writes = False
