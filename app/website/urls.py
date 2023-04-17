from django.urls import path
from django.views.generic import TemplateView

urlpatterns = [
    path("", TemplateView.as_view(template_name="index.html"), name="home"),
    path("ads", TemplateView.as_view(template_name="ads/list.html"), name="ads_list"),
    path("ads/new", TemplateView.as_view(template_name="ads/new.html"), name="ads_new"),
    path(
        "ads/<int:pk>",
        TemplateView.as_view(template_name="ads/detail.html"),
        name="ads_detail",
    ),
]
