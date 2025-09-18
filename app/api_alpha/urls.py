from django.urls import include
from django.urls import path
from django.urls import re_path
from rest_framework import routers

from api_alpha.endpoints.buildings.list_create_buildings import ListCreateBuildings
from api_alpha.endpoints.buildings.single_building import SingleBuilding
from api_alpha.endpoints.buildings.single_building import SingleBuildingHistory
from api_alpha.endpoints.tiles.ads_vector_tile import ADSVectorTileView
from api_alpha.endpoints.tiles.building_vector_tile import BuildingsShapeVectorTileView
from api_alpha.endpoints.tiles.building_vector_tile import BuildingsVectorTileView
from api_alpha.endpoints.tiles.plots_vector_tile import PlotsVectorTileView
from api_alpha.views import ActivateUser
from api_alpha.views import AdsTokenView
from api_alpha.views import ADSViewSet
from api_alpha.views import BuildingAddressView
from api_alpha.views import BuildingClosestView
from api_alpha.views import BuildingGuessView
from api_alpha.views import BuildingPlotView
from api_alpha.views import ChangePassword
from api_alpha.views import ContributionsViewSet
from api_alpha.views import CreateUserView
from api_alpha.views import DiffusionDatabaseView
from api_alpha.views import DiffView
from api_alpha.views import get_schema
from api_alpha.views import get_stats
from api_alpha.views import get_summer_challenge_leaderboard
from api_alpha.views import get_summer_challenge_user_score
from api_alpha.views import GetCurrentUserTokens
from api_alpha.views import GetUserToken
from api_alpha.views import MergeBuildings
from api_alpha.views import OrganizationView
from api_alpha.views import RequestPasswordReset
from api_alpha.views import RNBAuthToken
from api_alpha.views import SplitBuildings

from pygeoapi.django_.urls import urlpatterns as ogc_urlpatterns


# Routers provide an easy way of automatically determining the URL conf.
router = routers.DefaultRouter()
router.register(r"contributions", ContributionsViewSet)
router.register(r"ads", ADSViewSet)


# Wire up our API using automatic URL routing.
# Additionally, we include login URLs for the browsable API.
urlpatterns = [
    path("ogc/", include(ogc_urlpatterns)),
    path("schema/", get_schema, name="schema"),
    path("stats", get_stats),
    # For site
    path("diffusion_databases", DiffusionDatabaseView.as_view()),
    path("organization_names", OrganizationView.as_view()),
    # Buildings
    path("buildings/", ListCreateBuildings.as_view()),
    path("buildings/guess/", BuildingGuessView.as_view()),
    path("buildings/closest/", BuildingClosestView.as_view()),
    path("buildings/address/", BuildingAddressView.as_view()),
    path("buildings/plot/<str:plot_id>/", BuildingPlotView.as_view()),
    path("buildings/diff/", DiffView.as_view()),
    path("buildings/merge/", MergeBuildings.as_view()),
    re_path(
        r"buildings/(?P<rnb_id>[0-9a-zA-Z]{4}-?[0-9a-zA-Z]{4}-?[0-9a-zA-Z]{4})/split/",
        SplitBuildings.as_view(),
    ),
    path(
        "buildings/<str:rnb_id>/history/",
        SingleBuildingHistory.as_view(),
    ),
    re_path(
        r"buildings/(?P<rnb_id>[0-9a-zA-Z]{4}-?[0-9a-zA-Z]{4}-?[0-9a-zA-Z]{4})/",
        SingleBuilding.as_view(),
    ),
    # ADS
    path("ads/token/", AdsTokenView.as_view()),
    path("ads/tiles/<int:x>/<int:y>/<int:z>.pbf", ADSVectorTileView.as_view()),
    # Buildings vector tiles
    path("tiles/<int:x>/<int:y>/<int:z>.pbf", BuildingsVectorTileView.as_view()),
    path(
        "tiles/shapes/<int:x>/<int:y>/<int:z>.pbf",
        BuildingsShapeVectorTileView.as_view(),
    ),
    # Plots vector tiles
    path("plots/tiles/<int:x>/<int:y>/<int:z>.pbf", PlotsVectorTileView.as_view()),
    # Authentification
    path("login/", RNBAuthToken.as_view()),
    path("auth/users/", CreateUserView.as_view()),
    path("auth/users/me/tokens", GetCurrentUserTokens.as_view()),
    path("auth/users/<str:user_email_b64>/token", GetUserToken.as_view()),
    path("auth/activate/<str:user_id_b64>/<str:token>/", ActivateUser.as_view()),
    path("auth/reset_password/", RequestPasswordReset.as_view()),
    path(
        "auth/change_password/<str:user_id_b64>/<str:token>", ChangePassword.as_view()
    ),
    path("editions/ranking/", get_summer_challenge_leaderboard),
    path("editions/ranking/<str:username>/", get_summer_challenge_user_score),
]


# The /ads/ prefix is blocked by the adblockers
# We create two sets of URLs to serve ADS on urls without /ads/ prefix
# They will be used on the website but do not have to be in the documentation
urlpatterns.append(
    path("permis/tiles/<int:x>/<int:y>/<int:z>.pbf", ADSVectorTileView.as_view())
)
router.register(r"permis", ADSViewSet, basename="permis")


# Add the router URLs to the urlpatterns
urlpatterns.append(path("", include(router.urls)))
