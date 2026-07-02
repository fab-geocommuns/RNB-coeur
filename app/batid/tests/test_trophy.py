import datetime
import uuid
from unittest import mock

from batid.models import City, SummerChallenge, Trophy
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


def _add_validation_on(user, dt):
    """Create a validation for the user with created_at forced to `dt`
    (created_at is auto_now_add, hence the post-create UPDATE)."""
    sc = SummerChallenge.objects.create(
        user=user, action="validation", rnb_id="RNBTESTID000", event_id=uuid.uuid4()
    )
    SummerChallenge.objects.filter(id=sc.id).update(created_at=dt)


def _add_consecutive_days(user, start, n):
    """Create one validation on each of n consecutive days starting at `start`
    (a tz-aware datetime)."""
    for i in range(n):
        _add_validation_on(user, start + datetime.timedelta(days=i))


def _add_validation_in_city(user, city):
    """Create a validation for the user located in `city`."""
    SummerChallenge.objects.create(
        user=user,
        action="validation",
        rnb_id="RNBTESTID000",
        event_id=uuid.uuid4(),
        city=city,
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
        self.assertEqual(trophy, {"trophy_type": "validateur", "level": 1})
        self.assertEqual(
            Trophy.objects.filter(
                user=self.user, trophy_type="validateur", level=1
            ).count(),
            1,
        )

    def test_hundred_validations_awards_level_2(self):
        """Input: 100 validations. Expected: trophy level 2, levels 1 and 2 both stored."""
        _add_validations(self.user, 100)
        trophy = Trophy.check_and_award_validateur(self.user)
        self.assertEqual(trophy, {"trophy_type": "validateur", "level": 2})
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
        self.assertEqual(trophy, {"trophy_type": "validateur", "level": 3})
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


# a tz-aware reference datetime at noon UTC (same calendar date in Europe/Paris)
NOON_UTC = datetime.datetime(2026, 6, 1, 12, 0, tzinfo=datetime.timezone.utc)


class TestTrophyCourseDeFond(TestCase):
    def setUp(self):
        self.user = ContributorUserFactory(username="runner")

    def test_six_consecutive_days_awards_nothing(self):
        """Input: validations on 6 consecutive days. Expected: None (below 7)."""
        _add_consecutive_days(self.user, NOON_UTC, 6)
        self.assertIsNone(Trophy.check_and_award_course_de_fond(self.user))

    def test_seven_consecutive_days_awards_level_1(self):
        """Input: validations on 7 consecutive days. Expected: level 1."""
        _add_consecutive_days(self.user, NOON_UTC, 7)
        self.assertEqual(
            Trophy.check_and_award_course_de_fond(self.user),
            {"trophy_type": "course_de_fond", "level": 1},
        )

    def test_twenty_one_consecutive_days_awards_level_2(self):
        """Input: validations on 21 consecutive days. Expected: level 2."""
        _add_consecutive_days(self.user, NOON_UTC, 21)
        self.assertEqual(
            Trophy.check_and_award_course_de_fond(self.user),
            {"trophy_type": "course_de_fond", "level": 2},
        )

    def test_forty_two_consecutive_days_awards_level_3(self):
        """Input: validations on 42 consecutive days. Expected: level 3."""
        _add_consecutive_days(self.user, NOON_UTC, 42)
        self.assertEqual(
            Trophy.check_and_award_course_de_fond(self.user),
            {"trophy_type": "course_de_fond", "level": 3},
        )

    def test_gap_breaks_streak(self):
        """Input: a 5-day run, a 1-day gap, then a 7-day run. Expected: level 1
        (longest run is 7, not 13)."""
        _add_consecutive_days(self.user, NOON_UTC, 5)
        _add_consecutive_days(self.user, NOON_UTC + datetime.timedelta(days=6), 7)
        self.assertEqual(
            Trophy.check_and_award_course_de_fond(self.user),
            {"trophy_type": "course_de_fond", "level": 1},
        )

    def test_multiple_validations_same_day_count_once(self):
        """Input: 10 validations all on the same day. Expected: None (streak of 1)."""
        for _ in range(10):
            _add_validation_on(self.user, NOON_UTC)
        self.assertIsNone(Trophy.check_and_award_course_de_fond(self.user))


class TestTrophyTourDeFrance(TestCase):
    # 20 fake stage cities
    CODES = [f"{i:05d}" for i in range(1, 21)]

    def setUp(self):
        self.user = ContributorUserFactory(username="grimpeur")
        self.cities = [
            City.objects.create(code_insee=code, name=f"ville_{code}")
            for code in self.CODES
        ]

    def _validate_in(self, n_cities):
        for city in self.cities[:n_cities]:
            _add_validation_in_city(self.user, city)

    def test_four_cities_awards_nothing(self):
        """Input: validations in 4 stage cities. Expected: None (below 5)."""
        self._validate_in(4)
        with mock.patch.object(Trophy, "TOUR_DE_FRANCE_2026_INSEE_CODES", self.CODES):
            self.assertIsNone(Trophy.check_and_award_tour_de_france(self.user))

    def test_five_cities_awards_level_1(self):
        """Input: validations in 5 stage cities. Expected: level 1."""
        self._validate_in(5)
        with mock.patch.object(Trophy, "TOUR_DE_FRANCE_2026_INSEE_CODES", self.CODES):
            self.assertEqual(
                Trophy.check_and_award_tour_de_france(self.user),
                {"trophy_type": "tour_de_france", "level": 1},
            )

    def test_fifteen_cities_awards_level_2(self):
        """Input: validations in 15 stage cities. Expected: level 2."""
        self._validate_in(15)
        with mock.patch.object(Trophy, "TOUR_DE_FRANCE_2026_INSEE_CODES", self.CODES):
            self.assertEqual(
                Trophy.check_and_award_tour_de_france(self.user),
                {"trophy_type": "tour_de_france", "level": 2},
            )

    def test_all_cities_awards_level_3(self):
        """Input: validations in all 20 stage cities. Expected: level 3."""
        self._validate_in(20)
        with mock.patch.object(Trophy, "TOUR_DE_FRANCE_2026_INSEE_CODES", self.CODES):
            self.assertEqual(
                Trophy.check_and_award_tour_de_france(self.user),
                {"trophy_type": "tour_de_france", "level": 3},
            )

    def test_same_city_counted_once(self):
        """Input: 6 validations all in the same stage city. Expected: None
        (1 distinct city, below 5)."""
        for _ in range(6):
            _add_validation_in_city(self.user, self.cities[0])
        with mock.patch.object(Trophy, "TOUR_DE_FRANCE_2026_INSEE_CODES", self.CODES):
            self.assertIsNone(Trophy.check_and_award_tour_de_france(self.user))

    def test_non_stage_cities_not_counted(self):
        """Input: validations in 5 cities that are NOT stage cities. Expected: None."""
        others = [
            City.objects.create(code_insee=f"9{i:04d}", name=f"hors_{i}")
            for i in range(5)
        ]
        for city in others:
            _add_validation_in_city(self.user, city)
        with mock.patch.object(Trophy, "TOUR_DE_FRANCE_2026_INSEE_CODES", self.CODES):
            self.assertIsNone(Trophy.check_and_award_tour_de_france(self.user))


class TestTrophySuperV(TestCase):
    def setUp(self):
        self.user_a = ContributorUserFactory(username="alice")
        self.user_b = ContributorUserFactory(username="bob")

    def test_leader_gets_badge(self):
        """Input: A has 5 validations, B has 3. Expected: A is awarded superv (single
        row), B gets nothing."""
        _add_validations(self.user_a, 5)
        _add_validations(self.user_b, 3)

        self.assertEqual(
            Trophy.check_and_award_superv(self.user_a),
            {"trophy_type": "superv", "level": 1},
        )
        self.assertIsNone(Trophy.check_and_award_superv(self.user_b))
        self.assertEqual(Trophy.objects.filter(trophy_type="superv").count(), 1)

    def test_badge_transfers_to_new_leader(self):
        """Input: A leads (5) and holds superv, then B overtakes with 7. Expected:
        superv transfers to B; still a single row; A no longer holds it."""
        _add_validations(self.user_a, 5)
        _add_validations(self.user_b, 3)
        Trophy.check_and_award_superv(self.user_a)

        _add_validations(self.user_b, 4)  # B now has 7
        self.assertEqual(
            Trophy.check_and_award_superv(self.user_b),
            {"trophy_type": "superv", "level": 1},
        )
        self.assertEqual(Trophy.objects.filter(trophy_type="superv").count(), 1)
        self.assertEqual(
            Trophy.objects.get(trophy_type="superv").user_id, self.user_b.id
        )

    def test_current_holder_gets_nothing(self):
        """Input: A is the leader and already holds superv; called again. Expected:
        None (no new award, no duplicate)."""
        _add_validations(self.user_a, 5)
        Trophy.check_and_award_superv(self.user_a)
        self.assertIsNone(Trophy.check_and_award_superv(self.user_a))
        self.assertEqual(Trophy.objects.filter(trophy_type="superv").count(), 1)

    def test_no_validations_awards_nothing(self):
        """Input: no validations at all. Expected: None, no superv row."""
        self.assertIsNone(Trophy.check_and_award_superv(self.user_a))
        self.assertEqual(Trophy.objects.filter(trophy_type="superv").count(), 0)


class TestTrophyCheckAndAwardAll(TestCase):
    def setUp(self):
        self.user = ContributorUserFactory(username="all_rounder")

    def test_returns_all_newly_unlocked(self):
        """Input: user reaches 10 validations (same day) and is the sole validator.
        Expected: list contains both 'validateur' level 1 and 'superv' level 1."""
        _add_validations(self.user, 10)
        results = Trophy.check_and_award_all(self.user)
        self.assertIn({"trophy_type": "validateur", "level": 1}, results)
        self.assertIn({"trophy_type": "superv", "level": 1}, results)

    def test_returns_empty_when_nothing_unlocked(self):
        """Input: another user leads with more validations; this user has 1 validation.
        Expected: empty list."""
        other = ContributorUserFactory(username="leader")
        _add_validations(other, 5)
        _add_validations(self.user, 1)
        self.assertEqual(Trophy.check_and_award_all(self.user), [])
