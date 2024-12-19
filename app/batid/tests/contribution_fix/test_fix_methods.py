from django.contrib.auth.models import User
from django.test import TransactionTestCase

from batid.exceptions import ContributionFixTooBroad
from batid.models import Building
from batid.models import Contribution
from batid.services.contribution_fix.fix_methods import fix_contributions_deactivate
from batid.services.contribution_fix.fix_methods import fix_contributions_demolish


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

        fix_contributions_deactivate(
            self.user, "c'est un bosquet", None, review_comment
        )

        fixed_contributions = Contribution.objects.filter(status="fixed").order_by(
            "rnb_id"
        )
        self.assertEqual(
            [c.rnb_id for c in fixed_contributions],
            ["building_1", "building_2", "building_4"],
        )

    def test_bulk_deactivate_email_only(self):
        email = "contact@jardin.fr"

        fix_contributions_deactivate(self.user, None, email, "c'est ok")

        fixed_contributions = Contribution.objects.filter(status="fixed").order_by(
            "rnb_id"
        )
        self.assertEqual(
            [c.rnb_id for c in fixed_contributions],
            ["building_1", "building_2", "building_3"],
        )

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
