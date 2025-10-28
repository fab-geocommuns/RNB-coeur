# import user
from django.contrib.auth.models import User


def get_RNB_team_user():
    return User.objects.get(username="Équipe RNB")
