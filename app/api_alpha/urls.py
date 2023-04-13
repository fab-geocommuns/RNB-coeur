from api_alpha.views import BuildingViewSet, CityViewSet
from django.urls import include, path
from rest_framework import routers

# Routers provide an easy way of automatically determining the URL conf.
router = routers.DefaultRouter()
router.register(r"buildings", BuildingViewSet)
router.register(r"city", CityViewSet)

# Wire up our API using automatic URL routing.
# Additionally, we include login URLs for the browsable API.
urlpatterns = [
    path("", include(router.urls))
    # path('api-auth/', include('rest_framework.urls', namespace='rest_framework'))
]
