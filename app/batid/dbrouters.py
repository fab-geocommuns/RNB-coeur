from batid.models import Guess


class RNBDBRouter(object):
    def db_for_read(self, model, **hints):
        if model == Guess:
            return "guess"
        return None

    def db_for_write(self, model, **hints):
        if model == Guess:
            return "guess"
        return None
