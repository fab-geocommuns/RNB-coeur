from io import StringIO
from unittest import mock

from api_alpha.utils.sandbox_client import SandboxClientError
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

DUPLICATE_BODY = '{"email":["Un utilisateur avec cette adresse email existe déjà."]}'


class BackfillSandboxUsersTest(TestCase):
    """Tests for the backfill_sandbox_users management command.

    The command reads production emails from a file, resolves them to local
    users, and creates their counterpart on the sandbox through SandboxClient.
    It is a dry run unless --apply is given, treats a duplicate 400 as an
    already-done account, and stops on the sandbox throttle (429) reporting
    what is left so the run can be resumed.
    """

    def setUp(self):
        self.alice = User.objects.create_user(
            username="alice",
            email="alice@example.test",
            first_name="Alice",
            last_name="Martin",
        )
        self.bob = User.objects.create_user(
            username="bob",
            email="bob@example.test",
            first_name="Bob",
            last_name="Durand",
        )

    def _run(self, emails, **kwargs):
        """Run the command with the emails piped through stdin."""
        out = StringIO()
        with mock.patch("sys.stdin", StringIO("\n".join(emails) + "\n")):
            call_command(
                "backfill_sandbox_users",
                "--emails-file",
                "-",
                "--sleep",
                "0",
                stdout=out,
                **kwargs,
            )
        return out.getvalue()

    @mock.patch("api_alpha.utils.sandbox_client.SandboxClient.create_user")
    def test_dry_run_sends_nothing(self, mock_create):
        """Without --apply, the command lists the accounts it would create and
        never calls the sandbox."""
        output = self._run(["alice@example.test", "bob@example.test"])

        mock_create.assert_not_called()
        self.assertIn("DRY RUN", output)
        self.assertIn("alice@example.test", output)
        self.assertIn("bob@example.test", output)

    @mock.patch("api_alpha.utils.sandbox_client.SandboxClient.create_user")
    def test_apply_creates_accounts_with_a_password(self, mock_create):
        """With --apply, each resolved user is sent to the sandbox with their
        production identity plus a generated password."""
        output = self._run(["alice@example.test", "bob@example.test"], apply=True)

        self.assertEqual(mock_create.call_count, 2)
        payload = mock_create.call_args_list[0].args[0]
        self.assertEqual(payload["email"], "alice@example.test")
        self.assertEqual(payload["username"], "alice")
        self.assertEqual(payload["first_name"], "Alice")
        self.assertEqual(payload["last_name"], "Martin")
        self.assertTrue(payload["password"])
        self.assertIn("created          : 2", output)

    @mock.patch("api_alpha.utils.sandbox_client.SandboxClient.create_user")
    def test_unknown_email_is_reported_and_skipped(self, mock_create):
        """An email with no matching production user is reported and not sent."""
        output = self._run(["ghost@example.test", "alice@example.test"], apply=True)

        self.assertEqual(mock_create.call_count, 1)
        self.assertIn("unknown in prod", output)
        self.assertIn("ghost@example.test", output)

    @mock.patch("api_alpha.utils.sandbox_client.SandboxClient.create_user")
    def test_duplicate_is_counted_as_already_present(self, mock_create):
        """A 400 saying the account exists means the sandbox already has it:
        counted as already present, not as a failure."""
        mock_create.side_effect = SandboxClientError(
            "boom", status_code=400, body=DUPLICATE_BODY
        )
        output = self._run(["alice@example.test"], apply=True)

        self.assertIn("already present  : 1", output)
        self.assertIn("failed           : 0", output)

    @mock.patch("api_alpha.utils.sandbox_client.SandboxClient.create_user")
    def test_throttle_stops_the_run_and_lists_the_remainder(self, mock_create):
        """On a 429 the command stops immediately and prints the users left to
        do, so the same list can be fed back to resume later."""
        mock_create.side_effect = SandboxClientError(
            "throttled", status_code=429, body=""
        )
        output = self._run(["alice@example.test", "bob@example.test"], apply=True)

        self.assertEqual(mock_create.call_count, 1)
        self.assertIn("created          : 0", output)
        self.assertIn("not attempted    : 2", output)
        self.assertIn("throttle", output.lower())

    @mock.patch("api_alpha.utils.sandbox_client.SandboxClient.create_user")
    def test_other_error_is_a_failure_and_does_not_stop_the_run(self, mock_create):
        """A non-duplicate, non-throttle error is reported as a failure while
        the rest of the list is still processed."""
        mock_create.side_effect = [
            SandboxClientError("nope", status_code=500, body="server error"),
            None,
        ]
        output = self._run(["alice@example.test", "bob@example.test"], apply=True)

        self.assertEqual(mock_create.call_count, 2)
        self.assertIn("created          : 1", output)
        self.assertIn("failed           : 1", output)

    @mock.patch("api_alpha.utils.sandbox_client.SandboxClient.create_user")
    def test_limit_caps_the_number_of_creations(self, mock_create):
        """--limit stops after N creations and leaves the rest not attempted."""
        output = self._run(
            ["alice@example.test", "bob@example.test"], apply=True, limit=1
        )

        self.assertEqual(mock_create.call_count, 1)
        self.assertIn("created          : 1", output)
        self.assertIn("not attempted    : 1", output)

    @mock.patch("api_alpha.utils.sandbox_client.SandboxClient.create_user")
    def test_duplicates_and_blank_lines_in_the_file_are_ignored(self, mock_create):
        """The same email twice, blank lines and # comments produce one call."""
        output = self._run(
            ["alice@example.test", "", "# a comment", "ALICE@example.test"], apply=True
        )

        self.assertEqual(mock_create.call_count, 1)
        self.assertIn("created          : 1", output)

    def test_empty_file_is_an_error(self):
        """A file with no usable email aborts instead of doing nothing silently."""
        with self.assertRaises(CommandError):
            self._run(["", "# only a comment"])
