from batid.views import can_rollback
from django import template

register = template.Library()


@register.simple_tag
def can_rollback_user(user):
    """Check if user can access rollback functionality."""
    return can_rollback(user)
