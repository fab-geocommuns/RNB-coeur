# file is commented for the moment, as we suppressed the BuildingStatus model
# and the ADS logic will need to be reworked later accordingly

# from datetime import date

# from django.test import TestCase

# from batid.models import BuildingADS, ADS

# # from batid.services.models_gears import BuildingADSGear
# from batid.tests.helpers import (
#     create_default_bdg,
#     create_grenoble,
#     create_default_ads,
#     dispatch_signals,
# )


# class TestBdgAdsToBdgStatus(TestCase):
#     def setUp(self):
#         self.city = create_grenoble()

#     # ##################
#     # Test BuildingADSGear.get_expected_bdg_status
#     # ##################

#     # willBeBuilt
#     def test_willBeBuilt(self):
#         bdg = create_default_bdg("willBeBuilt")
#         ads = create_default_ads(city=self.city)
#         op = BuildingADS.objects.create(building=bdg, ads=ads, operation="build")

#         gear = BuildingADSGear(op)
#         status = gear.get_expected_bdg_status()

#         self.assertEqual(len(status), 1)
#         self.assertEqual(status[0].type, "constructionProject")
#         self.assertEqual(status[0].building, bdg)

#     # willBeBuilt + achieved_at
#     def test_willBeBuiltAchieved(self):
#         bdg = create_default_bdg("isDone")
#         ads = ADS.objects.create(
#             city=self.city, file_number="allDone", achieved_at="2023-01-01"
#         )
#         ads.refresh_from_db()  # We do so to get the achieved_at field

#         op = BuildingADS.objects.create(building=bdg, ads=ads, operation="build")

#         gear = BuildingADSGear(op)
#         status = gear.get_expected_bdg_status()

#         self.assertEqual(len(status), 2)

#         # constructionProject
#         self.assertEqual(status[0].type, "constructionProject")
#         self.assertEqual(status[0].building, bdg)
#         self.assertEqual(status[0].happened_at, ads.decided_at)
#         # constructed
#         self.assertEqual(status[1].type, "constructed")
#         self.assertEqual(status[1].building, bdg)
#         self.assertEqual(status[1].happened_at, ads.achieved_at)

#     # willBeDemolished
#     def test_willBeDemolished(self):
#         bdg = create_default_bdg("willBeDemo")
#         ads = ADS.objects.create(city=self.city, file_number="willBeDemo")
#         op = BuildingADS.objects.create(building=bdg, ads=ads, operation="demolish")

#         gear = BuildingADSGear(op)
#         status = gear.get_expected_bdg_status()

#         self.assertEqual(len(status), 0)

#     # willBeDemolished + achieved_at
#     def test_willBeDemolishedAchieved(self):
#         bdg = create_default_bdg("demoDone")
#         ads = ADS.objects.create(
#             city=self.city, file_number="allDone", achieved_at="2023-01-01"
#         )
#         ads.refresh_from_db()  # We do so to get the achieved_at field

#         op = BuildingADS.objects.create(building=bdg, ads=ads, operation="demolish")

#         gear = BuildingADSGear(op)
#         status = gear.get_expected_bdg_status()

#         self.assertEqual(len(status), 1)

#         # demolished
#         self.assertEqual(status[0].type, "demolished")
#         self.assertEqual(status[0].building, bdg)
#         self.assertEqual(status[0].happened_at, ads.achieved_at)

#     # willBeModified
#     def test_willBeModified(self):
#         bdg = create_default_bdg("willBeMod")
#         ads = ADS.objects.create(city=self.city, file_number="willBeMod")
#         op = BuildingADS.objects.create(building=bdg, ads=ads, operation="modify")

#         gear = BuildingADSGear(op)
#         status = gear.get_expected_bdg_status()

#         self.assertEqual(len(status), 0)

#     # willBeModified + achieved_at
#     def test_willBeModifiedAchieved(self):
#         bdg = create_default_bdg("modDone")
#         ads = ADS.objects.create(
#             city=self.city, file_number="modDone", achieved_at="2023-01-01"
#         )
#         ads.refresh_from_db()  # We do so to get the achieved_at field

#         op = BuildingADS.objects.create(building=bdg, ads=ads, operation="modify")

#         gear = BuildingADSGear(op)
#         status = gear.get_expected_bdg_status()

#         self.assertEqual(len(status), 0)

#     # # ##################
#     # Test integrations scenarios
#     # ##################

#     def test_singleOperation(self):
#         bdg = create_default_bdg("singleOp")
#         ads = ADS.objects.create(city=self.city, file_number="singleOp")
#         BuildingADS.objects.create(building=bdg, ads=ads, operation="build")

#         # We dispatch everything
#         dispatch_signals()
#         bdg.refresh_from_db()

#         self.assertEqual(bdg.status, "constructionProject")

#     # willBeBuilt > willBeModified > willBeBuilt
#     def test_multiOperationChange(self):
#         bdg = create_default_bdg("multiOp")
#         ads = ADS.objects.create(city=self.city, file_number="multiOp")

#         # Successive operations
#         op = BuildingADS.objects.create(building=bdg, ads=ads, operation="build")
#         dispatch_signals()

#         op.operation = "modify"
#         op.save()
#         dispatch_signals()

#         op.operation = "build"
#         op.save()
#         dispatch_signals()

#         # We refresh to check the status infos
#         bdg.refresh_from_db()

#         # We check the status
#         self.assertEqual(len(bdg.status.all()), 1)
#         self.assertEqual(bdg.status, "constructionProject")

#     # willBeBuilt > achieved_at
#     def test_builtAchieved(self):
#         bdg = create_default_bdg("builtDone")
#         ads = ADS.objects.create(
#             city=self.city, file_number="builtAchieved", decided_at="2023-01-01"
#         )
#         BuildingADS.objects.create(building=bdg, ads=ads, operation="build")
#         dispatch_signals()

#         # Later we achieve the ADS
#         ads.achieved_at = "2023-01-02"
#         ads.save()
#         ads.refresh_from_db()
#         dispatch_signals()

#         # We refresh to check the status infos
#         bdg.refresh_from_db()

#         self.assertEqual(len(bdg.status.all()), 2)

#         # constructionProject
#         self.assertEqual(bdg.status.all()[0].type, "constructionProject")
#         self.assertEqual(bdg.status.all()[0].building, bdg)
#         self.assertEqual(bdg.status.all()[0].happened_at, ads.decided_at)
#         self.assertEqual(bdg.status.all()[0].is_current, False)
#         # constructed
#         self.assertEqual(bdg.status.all()[1].type, "constructed")
#         self.assertEqual(bdg.status.all()[1].building, bdg)
#         self.assertEqual(bdg.status.all()[1].happened_at, ads.achieved_at)
#         self.assertEqual(bdg.status.all()[1].is_current, True)

#     # willBeModified > achieved_at
#     def test_modifiedAchieved(self):
#         bdg = create_default_bdg("modDone")
#         ads = ADS.objects.create(
#             city=self.city, file_number="modDone", decided_at="2023-01-01"
#         )
#         BuildingADS.objects.create(building=bdg, ads=ads, operation="modify")
#         dispatch_signals()

#         # Later we achieve the ADS
#         ads.achieved_at = "2023-01-03"
#         ads.save()
#         ads.refresh_from_db()
#         dispatch_signals()

#         # We refresh to check the status infos
#         bdg.refresh_from_db()

#         self.assertEqual(len(bdg.status.all()), 0)

#     # willBeDemolished > achieved_at
#     def test_demolishedAchieved(self):
#         bdg = create_default_bdg("demoDone")
#         ads = ADS.objects.create(
#             city=self.city, file_number="demoDone", decided_at="2023-01-01"
#         )
#         BuildingADS.objects.create(building=bdg, ads=ads, operation="demolish")
#         dispatch_signals()

#         # Later we achieve the ADS
#         ads.achieved_at = "2023-01-03"
#         ads.save()
#         ads.refresh_from_db()
#         dispatch_signals()

#         # We refresh to check the status infos
#         bdg.refresh_from_db()

#         self.assertEqual(len(bdg.status.all()), 2)

#         # constructed
#         self.assertEqual(bdg.status.all()[0].type, "constructed")
#         self.assertEqual(bdg.status.all()[0].building, bdg)
#         self.assertIsNone(bdg.status.all()[0].happened_at)
#         self.assertEqual(bdg.status.all()[0].is_current, False)
#         # demolished
#         self.assertEqual(bdg.status.all()[1].type, "demolished")
#         self.assertEqual(bdg.status.all()[1].building, bdg)
#         self.assertEqual(bdg.status.all()[1].happened_at, ads.achieved_at)
#         self.assertEqual(bdg.status.all()[1].is_current, True)

#     def test_fullCycle(self):
#         old_house = create_default_bdg("oldHouse")
#         bdg = create_default_bdg("fullCycle")

#         # First it is a building project, decided in the to celebrate the first man on the moon. An old house is demolished to build the new one
#         ads = ADS.objects.create(
#             city=self.city, file_number="create", decided_at="1969-07-21"
#         )
#         BuildingADS.objects.create(building=bdg, ads=ads, operation="build")
#         BuildingADS.objects.create(building=old_house, ads=ads, operation="demolish")
#         dispatch_signals()

#         # It is achieved years later, during a beautiful summer
#         ads.achieved_at = "1972-08-15"
#         ads.save()
#         ads.refresh_from_db()

#         # In 1984, a part of the building is demolished and rebuilt. The modification is quite fast
#         ads = ADS.objects.create(
#             city=self.city, file_number="modify", decided_at="1984-03-18"
#         )
#         BuildingADS.objects.create(building=bdg, ads=ads, operation="modify")
#         dispatch_signals()

#         # The modification is finished a few months later during a shitty winter
#         ads.achieved_at = "1984-12-24"
#         ads.save()
#         dispatch_signals()

#         # Finally, in 2019, it is a decided that the building will be demolished
#         ads = ADS.objects.create(
#             city=self.city, file_number="demolish", decided_at="2019-01-01"
#         )
#         BuildingADS.objects.create(building=bdg, ads=ads, operation="demolish")
#         dispatch_signals()

#         # The demolition is achieved three years later
#         ads.achieved_at = "2022-01-01"
#         ads.save()
#         dispatch_signals()

#         # We check everything is fine
#         bdg.refresh_from_db()

#         self.assertEqual(len(bdg.status.all()), 3)

#         # build a date

#         # constructionProject
#         self.assertEqual(bdg.status.all()[0].type, "constructionProject")
#         self.assertEqual(bdg.status.all()[0].building, bdg)
#         self.assertEqual(bdg.status.all()[0].happened_at, date(1969, 7, 21))
#         self.assertEqual(bdg.status.all()[0].is_current, False)
#         # constructed
#         self.assertEqual(bdg.status.all()[1].type, "constructed")
#         self.assertEqual(bdg.status.all()[1].building, bdg)
#         self.assertEqual(bdg.status.all()[1].happened_at, date(1972, 8, 15))
#         self.assertEqual(bdg.status.all()[1].is_current, False)
#         # demolished
#         self.assertEqual(bdg.status.all()[2].type, "demolished")
#         self.assertEqual(bdg.status.all()[2].building, bdg)
#         self.assertEqual(bdg.status.all()[2].happened_at, date(2022, 1, 1))
#         self.assertEqual(bdg.status.all()[2].is_current, True)

# willBeBuilt > willBeModified > achieved_at > willBeBuilt

# ###
# On buildings with previous, unrelated status
# ###
# constructionProject + constructed > willBeDemolished > achieved_at
# constructed > willBeDemolished > achieved_at
# constructionProject + constructed > willBeModified > achieved_at
# constructed > willBeModified > achieved_at
