from django.urls import path
from . import views

urlpatterns = [path("scaleway/<secret_token>", views.scaleway)]
