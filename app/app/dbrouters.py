# app/dbrouters.py
from batid.models import BuildingWithHistory, BuildingHistoryOnly


class DBRouter(object):
    def db_for_write(self, model, **hints):
        if model == BuildingWithHistory or model == BuildingHistoryOnly:
            raise Exception("BuildingWithHistory model is read only!")
        return None
