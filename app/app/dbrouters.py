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

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        """
        Make sure the auth and contenttypes apps only appear in the
        'auth_db' database.
        """
        if model_name == "guess":
            return db == "guess"
        else:
            return db == "default"
