# app/dbrouters.py
from batid.models import (
    BuildingAddressesInternalIdReadOnly,
    BuildingHistoryOnly,
    BuildingWithHistory,
)


class DBRouter(object):
    def db_for_write(self, model, **hints):

        if model == BuildingWithHistory or model == BuildingHistoryOnly:
            raise Exception("BuildingWithHistory model is read only!")
        if model == BuildingAddressesInternalIdReadOnly:
            raise Exception(
                "BuildingAddressesInternalIdReadOnly model is read only, as the name "
                "suggests! The links are maintained by a trigger from "
                "Building.addresses_internal_id."
            )
        return None
