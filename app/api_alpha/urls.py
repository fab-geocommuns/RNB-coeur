from django.urls import include
from django.urls import path
from django.urls import re_path
from rest_framework import routers

from api_alpha.endpoints.buildings.list_create_buildings import ListCreateBuildings
from api_alpha.endpoints.buildings.plot import BuildingPlotView
from api_alpha.endpoints.buildings.single_building import SingleBuilding
from api_alpha.endpoints.buildings.single_building import SingleBuildingHistory
from api_alpha.endpoints.ogc.views import OGCBuildingItemsView
from api_alpha.endpoints.ogc.views import OGCBuildingsCollectionView
from api_alpha.endpoints.ogc.views import OGCCollectionsView
from api_alpha.endpoints.ogc.views import OGCConformanceView
from api_alpha.endpoints.ogc.views import OGCIndexView
from api_alpha.endpoints.ogc.views import OGCOpenAPIDefinitionView
from api_alpha.endpoints.ogc.views import OGCSingleBuildingItemView
from api_alpha.endpoints.reports.create_report import CreateReportView
from api_alpha.endpoints.reports.get_report import GetReport
from api_alpha.endpoints.reports.reply_to_report import ReplyToReportView
from api_alpha.endpoints.reports.stats import ReportStatsView
from api_alpha.endpoints.tiles.ads_vector_tile import ADSVectorTileView
from api_alpha.endpoints.tiles.building_vector_tile import BuildingsShapeVectorTileView
from api_alpha.endpoints.tiles.building_vector_tile import BuildingsVectorTileView
from api_alpha.endpoints.tiles.plots_vector_tile import PlotsVectorTileView
from api_alpha.endpoints.tiles.report_vector_tile import ReportVectorTileView
from api_alpha.views import ActivateUser
from api_alpha.views import AdsTokenView
from api_alpha.views import ADSViewSet
from api_alpha.views import BuildingAddressView
from api_alpha.views import BuildingClosestView
from api_alpha.views import BuildingGuessView
from api_alpha.views import ChangePassword
from api_alpha.views import CreateUserView
from api_alpha.views import DiffusionDatabaseView
from api_alpha.views import DiffView
from api_alpha.views import get_all_endpoints_schema
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


# Routers provide an easy way of automatically determining the URL conf.
router = routers.DefaultRouter()
router.register(r"ads", ADSViewSet)


# Wire up our API using automatic URL routing.
# Additionally, we include login URLs for the browsable API.
urlpatterns = [
    path("schema/", get_all_endpoints_schema, name="schema"),
    path("stats", get_stats),
    # OGC API Features minimal endpoints
    path("ogc/", OGCIndexView.as_view(), name="ogc_root"),
    path("ogc/openapi", OGCOpenAPIDefinitionView.as_view(), name="ogc_openapi"),
    path("ogc/conformance", OGCConformanceView.as_view(), name="ogc_conformance"),
    path("ogc/collections", OGCCollectionsView.as_view(), name="ogc_collections"),
    path(
        "ogc/collections/buildings",
        OGCBuildingsCollectionView.as_view(),
        name="ogc_buildings_collection",
    ),
    path(
        "ogc/collections/buildings/items",
        OGCBuildingItemsView.as_view(),
        name="ogc_buildings_items",
    ),
    path(
        "ogc/collections/buildings/items/<str:featureId>",
        OGCSingleBuildingItemView.as_view(),
        name="ogc_single_building_item",
    ),
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
    # Vector tiles
    path("ads/tiles/<int:x>/<int:y>/<int:z>.pbf", ADSVectorTileView.as_view()),
    path("tiles/<int:x>/<int:y>/<int:z>.pbf", BuildingsVectorTileView.as_view()),
    path(
        "tiles/shapes/<int:x>/<int:y>/<int:z>.pbf",
        BuildingsShapeVectorTileView.as_view(),
    ),
    path("plots/tiles/<int:x>/<int:y>/<int:z>.pbf", PlotsVectorTileView.as_view()),
    path("reports/tiles/<int:x>/<int:y>/<int:z>.pbf", ReportVectorTileView.as_view()),
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
    # Reports
    path("reports/", CreateReportView.as_view()),
    path(
        "contributions/", CreateReportView.as_view()
    ),  # For backward compatibility of frontend
    path("reports/stats/", ReportStatsView.as_view()),
    path("reports/<int:report_id>/", GetReport.as_view()),
    path("reports/<int:report_id>/reply/", ReplyToReportView.as_view()),
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
