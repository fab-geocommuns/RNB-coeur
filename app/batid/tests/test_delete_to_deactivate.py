from django.test import TransactionTestCase

from batid.models import Building, BuildingWithHistory
from batid.services.data_fix.delete_to_deactivate import delete_to_deactivate


class DeleteToDeactivate(TransactionTestCase):

    def setUp(self):

        Building.objects.create(rnb_id="TRIGGER_ONE", event_type=None)

        Building.objects.create(rnb_id="WAS_DELETE", event_type="delete")
        Building.objects.create(rnb_id="WAS_DELETION", event_type="deletion")

        Building.objects.create(rnb_id="TRIGGER_TWO", event_type="creation")

    def test_delete_to_deactivate(self):

        # #######
        # Verify the trigger works before

        bdg = Building.objects.get(rnb_id="TRIGGER_ONE")
        bdg.status = "demolished"
        bdg.save()

        bdg_versions = BuildingWithHistory.objects.filter(rnb_id="TRIGGER_ONE")
        self.assertEqual(len(bdg_versions), 2)

        # #####
        # Verify the change of event_type is made w/o triggering the trigger

        delete_to_deactivate()

        # Test we have the right number of buildings of each event_type
        self.assertEqual(Building.objects.filter(event_type="deactivation").count(), 2)
        self.assertEqual(Building.objects.filter(event_type="delete").count(), 0)
        self.assertEqual(Building.objects.filter(event_type="deletion").count(), 0)
        self.assertEqual(Building.objects.filter(event_type="creation").count(), 1)

        # Verify that the trigger has not been triggered
        bdg_versions = BuildingWithHistory.objects.filter(rnb_id="WAS_DELETE")
        self.assertEqual(len(bdg_versions), 1)

        bdg_versions = BuildingWithHistory.objects.filter(rnb_id="WAS_DELETION")
        self.assertEqual(len(bdg_versions), 1)

        # #######
        # Verify the trigger is re-enabled
        bdg = Building.objects.get(rnb_id="TRIGGER_TWO")
        bdg.status = "demolished"
        bdg.save()

        bdg_versions = BuildingWithHistory.objects.filter(rnb_id="TRIGGER_TWO")
        self.assertEqual(len(bdg_versions), 2)
