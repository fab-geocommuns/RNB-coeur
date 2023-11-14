from api_alpha.views import (
    ADSViewSet,
    ADSBatchViewSet,
    BuildingViewSet,
    BuildingGuessView,
    BuildingTilesView,
)
from django.urls import include, path
from rest_framework import routers
from rest_framework.authtoken import views as auth_views

# Routers provide an easy way of automatically determining the URL conf.
router = routers.DefaultRouter()
# router.register(r"buildings/guess", BuildingGuessView, basename="guess")
router.register(r"buildings", BuildingViewSet)
router.register(r"ads/batch", ADSBatchViewSet)
router.register(r"ads", ADSViewSet)

# Wire up our API using automatic URL routing.
# Additionally, we include login URLs for the browsable API.
urlpatterns = [
    path("buildings/guess/", BuildingGuessView.as_view()),
    path("", include(router.urls)),
    path("login/", auth_views.obtain_auth_token),
    path("tiles/<int:x>/<int:y>/<int:z>.pbf", BuildingTilesView.as_view())
    # path('api-auth/', include('rest_framework.urls', namespace='rest_framework'))
]
