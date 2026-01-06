"""
Custom Django test runner that disables the event detail trigger during tests.

The trigger `building_versioning_trigger__1_insert_or_update_event_detail_trigger`
requires cities and departments to be present in the database to work correctly.
Since tests typically don't have this data, we disable the trigger during tests.
"""

from django.db import connection
from django.test.runner import DiscoverRunner


class RNBTestRunner(DiscoverRunner):
    """
    Custom test runner that disables the event detail trigger after database setup.
    """

    def setup_databases(self, **kwargs):
        """
        Set up the test databases and disable the event detail trigger.
        """
        result = super().setup_databases(**kwargs)
        self._disable_event_detail_trigger()
        return result

    def _disable_event_detail_trigger(self):
        """
        Disable the event detail trigger on batid_building table.

        The trigger `building_versioning_trigger__1_insert_or_update_event_detail_trigger`
        requires cities and departments data to compute event details.
        Since tests typically don't have this geographical data, we disable the trigger.
        """
        with connection.cursor() as cursor:
            cursor.execute(
                """
                ALTER TABLE batid_building
                DISABLE TRIGGER building_versioning_trigger__1_insert_or_update_event_detail_trigger;
                """
            )
