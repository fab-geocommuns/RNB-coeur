import sys
import time

from api_alpha.utils.sandbox_client import SandboxClient, SandboxClientError
from batid.services.sandbox import build_sandbox_user_payload
from batid.utils.auth import make_random_password
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

# The sandbox signup endpoint is throttled per IP (create_user, 10/day). A backfill
# calls it from a single IP, so a large run is expected to be throttled part way
# through. The command stops on the first 429 and reports what is left to do,
# so it can simply be run again later.
THROTTLED_STATUS = 429


class Command(BaseCommand):
    help = (
        "Create the missing sandbox counterparts of production users. "
        "Reads the target emails from a file (one per line, '-' for stdin). "
        "Runs as a dry run unless --apply is given."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--emails-file",
            required=True,
            help="file holding one production email per line, or '-' to read stdin",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="actually create the accounts (without it, nothing is sent)",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="stop after this many creations (useful to stay under the throttle)",
        )
        parser.add_argument(
            "--sleep",
            type=float,
            default=1.0,
            help="seconds to wait between two calls (default: 1.0)",
        )

    def handle(self, *args, **options):
        emails = self._read_emails(options["emails_file"])
        if not emails:
            raise CommandError("No email to process")

        users, unknown = self._resolve_users(emails)

        self.stdout.write(f"emails read       : {len(emails)}")
        self.stdout.write(f"matched in prod   : {len(users)}")
        if unknown:
            self.stdout.write(self.style.WARNING(f"unknown in prod   : {len(unknown)}"))
            for email in unknown:
                self.stdout.write(f"  ? {email}")

        if not options["apply"]:
            self.stdout.write(
                self.style.WARNING(
                    "\nDRY RUN — nothing sent. Accounts that would be created:"
                )
            )
            for user in users:
                self.stdout.write(f"  + {user.email} (username={user.username})")
            self.stdout.write("\nRe-run with --apply to create them.")
            return

        self._create_accounts(users, options["limit"], options["sleep"])

    def _read_emails(self, path):
        """Read one email per line, ignoring blanks, comments and duplicates."""
        handle = sys.stdin if path == "-" else open(path, encoding="utf-8")
        try:
            lines = handle.readlines()
        finally:
            if handle is not sys.stdin:
                handle.close()

        emails = []
        seen = set()
        for line in lines:
            email = line.strip()
            if not email or email.startswith("#"):
                continue
            if email.lower() not in seen:
                seen.add(email.lower())
                emails.append(email)
        return emails

    def _resolve_users(self, emails):
        """Map emails to production users, keeping the file order."""
        users = []
        unknown = []
        for email in emails:
            user = User.objects.filter(email__iexact=email).first()
            if user is None:
                unknown.append(email)
            else:
                users.append(user)
        return users, unknown

    def _create_accounts(self, users, limit, sleep):
        client = SandboxClient()
        created, skipped, failed, remaining = [], [], [], []
        throttled = False

        for index, user in enumerate(users):
            if throttled or (limit is not None and len(created) >= limit):
                remaining.append(user)
                continue

            payload = build_sandbox_user_payload(user)
            payload["password"] = make_random_password(length=24)

            try:
                client.create_user(payload)
                created.append(user)
                self.stdout.write(self.style.SUCCESS(f"  + {user.email}"))
            except SandboxClientError as error:
                if error.status_code == THROTTLED_STATUS:
                    # Every later call would be throttled too: stop here.
                    self.stdout.write(
                        self.style.WARNING(f"  ! throttled on {user.email}, stopping")
                    )
                    throttled = True
                    remaining.append(user)
                elif error.status_code == 400 and self._is_duplicate(error):
                    skipped.append(user)
                    self.stdout.write(f"  = {user.email} (already in sandbox)")
                else:
                    failed.append((user, error))
                    self.stdout.write(
                        self.style.ERROR(f"  x {user.email}: {error} {error.body}")
                    )

            if sleep and index < len(users) - 1:
                time.sleep(sleep)

        self._report(created, skipped, failed, remaining, throttled)

    def _is_duplicate(self, error):
        """The sandbox serializer rejects an existing email or username with a 400."""
        return "existe" in error.body.lower()

    def _report(self, created, skipped, failed, remaining, throttled):
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(f"created          : {len(created)}")
        self.stdout.write(f"already present  : {len(skipped)}")
        self.stdout.write(f"failed           : {len(failed)}")
        self.stdout.write(f"not attempted    : {len(remaining)}")

        if failed:
            self.stdout.write(self.style.ERROR("\nFailures:"))
            for user, error in failed:
                self.stdout.write(f"  {user.email}  {error}")

        if remaining:
            self.stdout.write(
                self.style.WARNING(
                    "\nStill to do — feed these back to the command to resume:"
                )
            )
            for user in remaining:
                self.stdout.write(user.email)

        if throttled:
            self.stdout.write(
                self.style.WARNING(
                    "\nStopped on the sandbox throttle (create_user, 10/day per IP)."
                )
            )
