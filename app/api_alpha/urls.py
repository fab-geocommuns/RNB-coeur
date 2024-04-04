from django.urls import include
from django.urls import path
from drf_spectacular.views import SpectacularAPIView
from drf_spectacular.views import SpectacularRedocView
from rest_framework import routers
from rest_framework.authtoken import views as auth_views

from api_alpha.views import ADSBatchViewSet
from api_alpha.views import ADSViewSet
from api_alpha.views import BuildingClosestView
from api_alpha.views import BuildingGuessView
from api_alpha.views import BuildingViewSet
from api_alpha.views import ContributionsViewSet
from api_alpha.views import get_tile

# Routers provide an easy way of automatically determining the URL conf.
router = routers.DefaultRouter()
# router.register(r"buildings/guess", BuildingGuessView, basename="guess")
router.register(r"contributions", ContributionsViewSet)
router.register(r"buildings", BuildingViewSet)
router.register(r"ads/batch", ADSBatchViewSet)
router.register(r"ads", ADSViewSet)

# Wire up our API using automatic URL routing.
# Additionally, we include login URLs for the browsable API.
urlpatterns = [
    # YOUR PATTERNS
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "schema/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"
    ),
    path("buildings/guess/", BuildingGuessView.as_view()),
    path("buildings/closest/", BuildingClosestView.as_view()),
    path("", include(router.urls)),
    path("login/", auth_views.obtain_auth_token),
    path("tiles/<int:x>/<int:y>/<int:z>.pbf", get_tile),
    # path('api-auth/', include('rest_framework.urls', namespace='rest_framework'))
]
