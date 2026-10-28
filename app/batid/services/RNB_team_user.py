# import user
from django.contrib.auth.models import User

# Technical account running the imports, rollbacks and automatic reports
RNB_TEAM_USERNAME = "RNB"


def get_RNB_team_user():
    return User.objects.get(username=RNB_TEAM_USERNAME)
