from django import template
from django.conf import settings
from django.templatetags.static import static

register = template.Library()


@register.simple_tag
def absolute_static(path):
    return f"{settings.URL}{static(path)}"
