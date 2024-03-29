# app/dbrouters.py
from batid.models import BuildingHistoryOnly
from batid.models import BuildingWithHistory
from batid.models import Guess


class DBRouter(object):
    def db_for_read(self, model, **hints):
        if model == Guess:
            return "guess"
        return None

    def db_for_write(self, model, **hints):
        if model == BuildingWithHistory or model == BuildingHistoryOnly:
            raise Exception("BuildingWithHistory model is read only!")
        if model == Guess:
            return "guess"
        return None
