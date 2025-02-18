from django.contrib.auth.models import User
from django.test import TransactionTestCase

from batid.exceptions import ContributionFixTooBroad
from batid.models import Address
from batid.models import Building
from batid.models import Contribution
from batid.services.contribution_fix.fix_methods import fix_contributions_deactivate
from batid.services.contribution_fix.fix_methods import fix_contributions_demolish
from batid.services.contribution_fix.fix_methods import (
    fix_contributions_merge_if_obvious,
)


class FixMethodTest(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create()
        self.building_1 = Building.objects.create(
            rnb_id="building_1", status="constructed", is_active=True
        )
        self.building_2 = Building.objects.create(
            rnb_id="building_2", status="constructed", is_active=True
        )
        self.building_3 = Building.objects.create(
            rnb_id="building_3", status="constructed", is_active=True
        )
        self.building_4 = Building.objects.create(
            rnb_id="building_4", status="constructed", is_active=True
        )

        self.contribution_1 = Contribution.objects.create(
            status="pending",
            rnb_id="building_1",
            text="c'est un bosquet",
            email="contact@jardin.fr",
        )
        self.contribution_2 = Contribution.objects.create(
            status="pending",
            rnb_id="building_2",
            text="c'est un bosquet",
            email="contact@jardin.fr",
        )
        self.contribution_3 = Contribution.objects.create(
            status="pending",
            rnb_id="building_3",
            text="plantez des arbres !",
            email="contact@jardin.fr",
        )
        self.contribution_4 = Contribution.objects.create(
            status="pending",
            rnb_id="building_4",
            text="c'est un bosquet",
            email="jean.du@jardin.fr",
        )

    def test_bulk_deactivate_comment_user(self):
        fixed_contributions_n = Contribution.objects.filter(status="fixed").count()
        self.assertEqual(fixed_contributions_n, 0)
        review_comment = (
            "nous pouvons faire confiance à cet utilisateur, c'est ma mère."
        )

        fix_contributions_deactivate(
            self.user, "c'est un bosquet", "contact@jardin.fr", review_comment
        )

        fixed_contributions = Contribution.objects.filter(status="fixed").order_by(
            "rnb_id"
        )
        self.assertEqual(
            [c.rnb_id for c in fixed_contributions], ["building_1", "building_2"]
        )

        self.assertEqual(fixed_contributions[0].review_comment, review_comment)
        self.assertEqual(fixed_contributions[0].review_user, self.user)

        self.assertEqual(fixed_contributions[1].review_comment, review_comment)
        self.assertEqual(fixed_contributions[1].review_user, self.user)

        self.building_1.refresh_from_db()
        self.assertEqual(self.building_1.is_active, False)
        self.assertEqual(self.building_1.event_type, "deactivation")
        self.assertEqual(self.building_1.event_user, self.user)

        self.building_2.refresh_from_db()
        self.assertEqual(self.building_2.is_active, False)
        self.assertEqual(self.building_2.event_type, "deactivation")
        self.assertEqual(self.building_2.event_user, self.user)

    def test_bulk_deactivate_comment_only(self):
        review_comment = (
            "nous pouvons faire confiance à cet utilisateur, c'est ma mère."
        )

        with self.assertRaises(ContributionFixTooBroad):
            fix_contributions_deactivate(
                self.user, "c'est un bosquet", None, review_comment
            )

    def test_bulk_deactivate_email_only(self):
        email = "contact@jardin.fr"

        with self.assertRaises(ContributionFixTooBroad):
            fix_contributions_deactivate(self.user, None, email, "c'est ok")

    def test_bulk_deactivate_nothing(self):
        with self.assertRaises(ContributionFixTooBroad):
            fix_contributions_deactivate(
                self.user, None, None, "Je désactive tout, j'en ai marre"
            )

    def test_bulk_demolish_comment_user(self):
        fixed_contributions_n = Contribution.objects.filter(status="fixed").count()
        self.assertEqual(fixed_contributions_n, 0)
        review_comment = "Ces bâtiments sont effectivement démolis."

        fix_contributions_demolish(
            self.user, "c'est un bosquet", "contact@jardin.fr", review_comment
        )

        fixed_contributions = Contribution.objects.filter(status="fixed").order_by(
            "rnb_id"
        )
        self.assertEqual(
            [c.rnb_id for c in fixed_contributions], ["building_1", "building_2"]
        )

        self.assertEqual(fixed_contributions[0].review_comment, review_comment)
        self.assertEqual(fixed_contributions[0].review_user, self.user)

        self.assertEqual(fixed_contributions[1].review_comment, review_comment)
        self.assertEqual(fixed_contributions[1].review_user, self.user)

        self.building_1.refresh_from_db()
        self.assertEqual(self.building_1.is_active, True)
        self.assertEqual(self.building_1.event_type, "update")
        self.assertEqual(self.building_1.event_user, self.user)
        self.assertEqual(self.building_1.status, "demolished")

        self.building_2.refresh_from_db()
        self.assertEqual(self.building_2.is_active, True)
        self.assertEqual(self.building_2.event_type, "update")
        self.assertEqual(self.building_2.event_user, self.user)
        self.assertEqual(self.building_1.status, "demolished")


class FixMergeTest(TransactionTestCase):
    def setUp(self):
        self.user = User.objects.create()
        self.adr1 = Address.objects.create(id="cle_interop_1")
        self.adr2 = Address.objects.create(id="cle_interop_2")

        # 3 buildings touching (1 is not active)
        self.building_1 = Building.objects.create(
            rnb_id="building_1",
            status="constructed",
            is_active=True,
            shape="POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
            addresses_id=[self.adr1.id],
        )

        self.building_2 = Building.objects.create(
            rnb_id="building_2",
            status="constructed",
            is_active=True,
            shape="POLYGON ((1 0, 1 1, 2 1, 2 0, 1 0))",
            addresses_id=[self.adr2.id],
        )
        self.building_3 = Building.objects.create(
            rnb_id="building_3",
            status="constructed",
            is_active=False,
            shape="POLYGON ((1 0, 1 1, 2 1, 2 0, 1 0))",
        )

        # alone
        self.building_4 = Building.objects.create(
            rnb_id="building_4",
            status="constructed",
            is_active=True,
            shape="POLYGON ((10 0, 10 1, 11 1, 11 0, 10 0))",
        )

        # 3 buildings touching
        self.building_5 = Building.objects.create(
            rnb_id="building_5",
            status="constructed",
            is_active=True,
            shape="POLYGON ((0 10, 0 11, 1 11, 1 10, 0 10))",
        )
        self.building_6 = Building.objects.create(
            rnb_id="building_6",
            status="constructed",
            is_active=True,
            shape="POLYGON ((0 10, 0 11, 1 11, 1 10, 0 10))",
        )
        self.building_7 = Building.objects.create(
            rnb_id="building_7",
            status="constructed",
            is_active=True,
            shape="POLYGON ((0 10, 0 11, 1 11, 1 10, 0 10))",
        )

    def test_bulk_merge(self):
        contribution_1 = Contribution.objects.create(
            status="pending",
            rnb_id="building_1",
            text="Il faut fusionner ce bâtiment",
            email="goten@akira.fr",
        )

        contribution_2 = Contribution.objects.create(
            status="pending",
            rnb_id="building_2",
            text="Il faut fusionner ce bâtiment",
            email="goten@akira.fr",
        )

        contribution_3 = Contribution.objects.create(
            status="pending",
            rnb_id="building_4",
            text="Il faut fusionner ce bâtiment",
            email="goten@akira.fr",
        )

        contribution_4 = Contribution.objects.create(
            status="pending",
            rnb_id="building_5",
            text="Il faut fusionner ce bâtiment",
            email="goten@akira.fr",
        )

        review_comment = "un pro de la fusion, on peut valider"
        fix_contributions_merge_if_obvious(
            self.user, "Il faut fusionner ce bâtiment", "goten@akira.fr", review_comment
        )

        contribution_1.refresh_from_db()
        contribution_2.refresh_from_db()
        contribution_3.refresh_from_db()
        contribution_4.refresh_from_db()

        self.assertEqual(contribution_1.status, "fixed")
        self.assertEqual(contribution_1.review_comment, review_comment)

        # refused during the merge process triggered by contribution_1
        self.assertEqual(contribution_2.status, "refused")
        self.assertEqual(
            contribution_2.review_comment,
            "Ce signalement a été refusé suite à la désactivation du bâtiment building_2.",
        )

        # not fixed because building_4 is alone
        self.assertEqual(contribution_3.status, "pending")
        self.assertEqual(contribution_3.review_comment, None)

        # not fixed because building_5 is touching too many buildings
        self.assertEqual(contribution_4.status, "pending")
        self.assertEqual(contribution_4.review_comment, None)

        self.building_1.refresh_from_db()
        self.assertFalse(self.building_1.is_active)
        self.assertEqual(self.building_1.event_type, "merge")
        event_id = self.building_1.event_id

        new_buildings = (
            Building.objects.filter(event_id=event_id).filter(is_active=True).all()
        )
        new_building = new_buildings[0]
        self.assertEqual(
            new_building.addresses_id.sort(), [self.adr1.id, self.adr2.id].sort()
        )
