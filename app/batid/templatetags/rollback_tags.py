from django import template

from batid.views import can_rollback

register = template.Library()


@register.simple_tag
def can_rollback_user(user):
    """Check if user can access rollback functionality."""
    return can_rollback(user)
