from django.contrib import admin
from rest_framework_tracking.admin import APIRequestLogAdmin
from rest_framework_tracking.models import APIRequestLog


class ReadOnlyAPIRequestLogAdmin(APIRequestLogAdmin):
    """API request logs are evidence: no one, superusers included, adds, edits or
    deletes one from the admin. They are only removed by the yearly purge."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# rest_framework_tracking comes before api_alpha in INSTALLED_APPS: its admin is
# already registered.
admin.site.unregister(APIRequestLog)
admin.site.register(APIRequestLog, ReadOnlyAPIRequestLogAdmin)
