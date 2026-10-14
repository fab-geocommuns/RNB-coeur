from batid.models import EmailNotificationOptOut
from django.test import TestCase


class EmailNotificationOptOutTest(TestCase):
    def test_opt_out_creates_row(self):
        """
        Input: opt_out("user@example.com") on an empty table.
        Expected: one opt-out row exists and is_opted_out returns True.
        """
        EmailNotificationOptOut.opt_out("user@example.com")
        self.assertTrue(EmailNotificationOptOut.is_opted_out("user@example.com"))
        self.assertEqual(EmailNotificationOptOut.objects.count(), 1)

    def test_opt_out_is_idempotent(self):
        """
        Input: opt_out called twice with the same email.
        Expected: a single row exists (get_or_create, unique constraint).
        """
        EmailNotificationOptOut.opt_out("user@example.com")
        EmailNotificationOptOut.opt_out("user@example.com")
        self.assertEqual(EmailNotificationOptOut.objects.count(), 1)

    def test_is_opted_out_false_when_absent(self):
        """
        Input: is_opted_out on an address that was never opted out.
        Expected: returns False.
        """
        self.assertFalse(EmailNotificationOptOut.is_opted_out("nobody@example.com"))

    def test_opt_in_removes_row(self):
        """
        Input: opt_out then opt_in for the same address.
        Expected: the row is deleted and is_opted_out returns False.
        """
        EmailNotificationOptOut.opt_out("user@example.com")
        EmailNotificationOptOut.opt_in("user@example.com")
        self.assertFalse(EmailNotificationOptOut.is_opted_out("user@example.com"))
        self.assertEqual(EmailNotificationOptOut.objects.count(), 0)

    def test_opt_in_when_absent_is_noop(self):
        """
        Input: opt_in on an address that is not opted out.
        Expected: no error, table stays empty.
        """
        EmailNotificationOptOut.opt_in("nobody@example.com")
        self.assertEqual(EmailNotificationOptOut.objects.count(), 0)

    def test_case_is_normalized(self):
        """
        Input: opt_out with an uppercase address, then queries with mixed case.
        Expected: stored lowercase; is_opted_out matches regardless of input case;
                  opt_in with another case removes the same row.
        """
        EmailNotificationOptOut.opt_out("User@Example.com")
        self.assertEqual(
            EmailNotificationOptOut.objects.get().email, "user@example.com"
        )
        self.assertTrue(EmailNotificationOptOut.is_opted_out("USER@EXAMPLE.COM"))
        EmailNotificationOptOut.opt_in("user@EXAMPLE.com")
        self.assertEqual(EmailNotificationOptOut.objects.count(), 0)
