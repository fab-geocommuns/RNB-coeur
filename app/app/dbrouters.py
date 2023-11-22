# app/dbrouters.py
from batid.models import BuildingWithHistory


class DBRouter(object):
    def db_for_write(self, model, **hints):
        if model == BuildingWithHistory:
            raise Exception("BuildingWithHistory model is read only!")
        return None
