from django.urls import include
from django.urls import path
from django.urls import re_path
from rest_framework import routers

from api_alpha.views import AdsTokenView
from api_alpha.views import ADSVectorTileView
from api_alpha.views import ADSViewSet
from api_alpha.views import BuildingAddressView
from api_alpha.views import BuildingClosestView
from api_alpha.views import BuildingGuessView
from api_alpha.views import BuildingPlotView
from api_alpha.views import BuildingsVectorTileView
from api_alpha.views import ContributionsViewSet
from api_alpha.views import DiffView
from api_alpha.views import get_schema
from api_alpha.views import get_stats
from api_alpha.views import get_tile_shape
from api_alpha.views import ListCreateBuildings
from api_alpha.views import PlotsVectorTileView
from api_alpha.views import RNBAuthToken
from api_alpha.views import SingleBuilding
from api_alpha.views import DiffusionDatabaseView

# Routers provide an easy way of automatically determining the URL conf.
router = routers.DefaultRouter()
router.register(r"contributions", ContributionsViewSet)
router.register(r"ads", ADSViewSet)


# Wire up our API using automatic URL routing.
# Additionally, we include login URLs for the browsable API.
urlpatterns = [
    path("schema/", get_schema, name="schema"),
    path("stats", get_stats),
    path("buildings/", ListCreateBuildings.as_view()),
    path("buildings/guess/", BuildingGuessView.as_view()),
    path("buildings/closest/", BuildingClosestView.as_view()),
    path("buildings/address/", BuildingAddressView.as_view()),
    path("buildings/plot/<str:plot_id>/", BuildingPlotView.as_view()),
    path("buildings/diff/", DiffView.as_view()),
    re_path(
        r"buildings/(?P<rnb_id>[0-9a-zA-Z]{4}-?[0-9a-zA-Z]{4}-?[0-9a-zA-Z]{4})/",
        SingleBuilding.as_view(),
    ),
    path("ads/token/", AdsTokenView.as_view()),
    path("ads/tiles/<int:x>/<int:y>/<int:z>.pbf", ADSVectorTileView.as_view()),
    path("login/", RNBAuthToken.as_view()),
    path("tiles/<int:x>/<int:y>/<int:z>.pbf", BuildingsVectorTileView.as_view()),
    path("tiles/shapes/<int:x>/<int:y>/<int:z>.pbf", get_tile_shape),
    # Plots vector tiles
    path("plots/tiles/<int:x>/<int:y>/<int:z>.pbf", PlotsVectorTileView.as_view()),
    path("diffusion_databases", DiffusionDatabaseView.as_view()),
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
