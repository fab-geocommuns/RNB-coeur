import uuid

from batid.models import SummerChallenge, Trophy
from batid.tests.factories.users import ContributorUserFactory
from django.test import TestCase


def _add_validations(user, n):
    """Create n SummerChallenge rows with action='validation' for the user."""
    for _ in range(n):
        SummerChallenge.objects.create(
            user=user,
            action="validation",
            rnb_id="RNBTESTID000",
            event_id=uuid.uuid4(),
        )


class TestTrophyValidateur(TestCase):
    def setUp(self):
        self.user = ContributorUserFactory(username="trophy_user")

    def test_below_first_threshold_awards_nothing(self):
        """Input: 9 validations. Expected: no trophy returned, no Trophy row created."""
        _add_validations(self.user, 9)
        self.assertIsNone(Trophy.check_and_award_validateur(self.user))
        self.assertEqual(Trophy.objects.count(), 0)

    def test_ten_validations_awards_level_1(self):
        """Input: 10 validations. Expected: trophy validateur level 1 + 1 Trophy row."""
        _add_validations(self.user, 10)
        trophy = Trophy.check_and_award_validateur(self.user)
        self.assertEqual(trophy, {"label": "validateur", "level": 1})
        self.assertEqual(
            Trophy.objects.filter(user=self.user, label="validateur", level=1).count(),
            1,
        )

    def test_hundred_validations_awards_level_2(self):
        """Input: 100 validations. Expected: trophy level 2, levels 1 and 2 both stored."""
        _add_validations(self.user, 100)
        trophy = Trophy.check_and_award_validateur(self.user)
        self.assertEqual(trophy, {"label": "validateur", "level": 2})
        self.assertEqual(
            sorted(
                Trophy.objects.filter(user=self.user).values_list("level", flat=True)
            ),
            [1, 2],
        )

    def test_five_hundred_validations_awards_level_3(self):
        """Input: 500 validations. Expected: trophy level 3, levels 1, 2, 3 stored."""
        _add_validations(self.user, 500)
        trophy = Trophy.check_and_award_validateur(self.user)
        self.assertEqual(trophy, {"label": "validateur", "level": 3})
        self.assertEqual(
            sorted(
                Trophy.objects.filter(user=self.user).values_list("level", flat=True)
            ),
            [1, 2, 3],
        )

    def test_idempotent_no_duplicate(self):
        """Input: level 1 already awarded, called again with same count. Expected:
        returns None and no duplicate Trophy row."""
        _add_validations(self.user, 10)
        Trophy.check_and_award_validateur(self.user)
        self.assertIsNone(Trophy.check_and_award_validateur(self.user))
        self.assertEqual(Trophy.objects.filter(user=self.user).count(), 1)

    def test_other_actions_not_counted(self):
        """Input: 10 SummerChallenge rows with action='creation'. Expected: no trophy,
        only action='validation' counts."""
        for _ in range(10):
            SummerChallenge.objects.create(
                user=self.user,
                action="creation",
                rnb_id="RNBTESTID000",
                event_id=uuid.uuid4(),
            )
        self.assertIsNone(Trophy.check_and_award_validateur(self.user))
        self.assertEqual(Trophy.objects.count(), 0)

    def test_none_user_returns_none(self):
        """Input: user=None. Expected: None, no Trophy row."""
        self.assertIsNone(Trophy.check_and_award_validateur(None))
        self.assertEqual(Trophy.objects.count(), 0)
