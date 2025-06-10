# app/dbrouters.py
from batid.models import BuildingAddressesReadOnly


class DBRouter(object):
    def db_for_write(self, model, **hints):

        if model == BuildingWithHistory or model == BuildingHistoryOnly:
            raise Exception("BuildingWithHistory model is read only!")
        if model == BuildingAddressesReadOnly:
            raise Exception(
                "BuildingAddressesReadOnly model is read only, as the name suggests!"
            )
        return None
