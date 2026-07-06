from batid.models import Trophy
from batid.tests.factories.users import ContributorUserFactory
from rest_framework.test import APITestCase


class TrophiesViewTest(APITestCase):
    def _by_trophy(self, body):
        return {t["trophy"]: t for t in body}

    def test_lists_all_earnable_trophies_with_zero_counts(self):
        """
        Input: no trophy has been awarded to anyone.
        Expected: 200; the 4 earnable trophies are listed in order, each with its
        trophy_label, a description, a total count of 0 and every level (with
        level_label and unlock condition) at count 0. 'superv' has a single,
        unnamed level.
        """
        r = self.client.get("/api/alpha/trophies/")

        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(
            [t["trophy"] for t in body],
            ["validateur", "course_de_fond", "tour_de_france", "superv"],
        )

        validateur = self._by_trophy(body)["validateur"]
        self.assertEqual(validateur["trophy_label"], "Validateur")
        self.assertEqual(validateur["count"], 0)
        self.assertEqual(
            validateur["levels"],
            [
                {
                    "level": 1,
                    "level_label": "bronze",
                    "condition": "Valider 10 bâtiments",
                    "count": 0,
                },
                {
                    "level": 2,
                    "level_label": "argent",
                    "condition": "Valider 100 bâtiments",
                    "count": 0,
                },
                {
                    "level": 3,
                    "level_label": "or",
                    "condition": "Valider 250 bâtiments",
                    "count": 0,
                },
            ],
        )

        superv = self._by_trophy(body)["superv"]
        self.assertEqual(superv["trophy_label"], "Super V")
        self.assertEqual(
            superv["description"],
            "Gagnez ce trophée en étant la personne qui a fait le plus de validation "
            "dans le RNB.",
        )
        self.assertEqual(
            superv["levels"],
            [
                {
                    "level": 1,
                    "level_label": None,
                    "condition": "Trophée unique : être la personne ayant réalisé le plus de validations dans le RNB... et le rester",
                    "count": 0,
                }
            ],
        )

    def test_counts_distinct_users_per_trophy_and_level(self):
        """
        Input: user A has validateur lvl 1 & 2 and course_de_fond lvl 1; user B has
        validateur lvl 1 and superv lvl 1.
        Expected: 200; validateur total count is 2 (A, B) with level counts 2/1/0;
        course_de_fond total 1 (level 1 only); tour_de_france total 0; superv total 1.
        """
        user_a = ContributorUserFactory(username="a")
        user_b = ContributorUserFactory(username="b")
        Trophy.objects.create(user=user_a, trophy_type="validateur", level=1)
        Trophy.objects.create(user=user_a, trophy_type="validateur", level=2)
        Trophy.objects.create(user=user_a, trophy_type="course_de_fond", level=1)
        Trophy.objects.create(user=user_b, trophy_type="validateur", level=1)
        Trophy.objects.create(user=user_b, trophy_type="superv", level=1)

        r = self.client.get("/api/alpha/trophies/")

        self.assertEqual(r.status_code, 200)
        by_trophy = self._by_trophy(r.json())

        validateur = by_trophy["validateur"]
        self.assertEqual(validateur["count"], 2)
        self.assertEqual([lvl["count"] for lvl in validateur["levels"]], [2, 1, 0])

        course_de_fond = by_trophy["course_de_fond"]
        self.assertEqual(course_de_fond["count"], 1)
        self.assertEqual([lvl["count"] for lvl in course_de_fond["levels"]], [1, 0, 0])

        self.assertEqual(by_trophy["tour_de_france"]["count"], 0)
        self.assertEqual(by_trophy["superv"]["count"], 1)
