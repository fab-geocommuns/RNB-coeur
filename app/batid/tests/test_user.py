from django.contrib.auth.models import User
from django.test import TestCase

from batid.services.user import get_staff_emails


class GetStaffEmailsTestCase(TestCase):
    def test_returns_active_staff_emails(self):
        """
        Input: 1 active staff user with email, 1 inactive staff, 1 non-staff.
        Expected: only the active staff user's email is returned.
        """
        User.objects.create_user("staff1", email="staff1@example.com", is_staff=True)
        User.objects.create_user(
            "inactive_staff",
            email="inactive@example.com",
            is_staff=True,
            is_active=False,
        )
        User.objects.create_user("regular", email="regular@example.com", is_staff=False)

        emails = get_staff_emails()

        self.assertEqual(emails, ["staff1@example.com"])

    def test_excludes_empty_email(self):
        """
        Input: 1 active staff user with empty email.
        Expected: empty list.
        """
        User.objects.create_user("staff_no_email", email="", is_staff=True)

        emails = get_staff_emails()

        self.assertEqual(emails, [])
