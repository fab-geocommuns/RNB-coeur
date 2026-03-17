from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from batid.services.email import build_monthly_leaderboard_email
from batid.utils.date import french_month_year_label
from batid.utils.date import previous_month


class Command(BaseCommand):
    help = "Build and send the monthly leaderboard email to staff users"

    def add_arguments(self, parser):
        parser.add_argument(
            "--year",
            type=int,
            help="Year of the leaderboard (defaults to previous month's year)",
        )
        parser.add_argument(
            "--month",
            type=int,
            help="Month of the leaderboard (defaults to previous month)",
        )

    def handle(self, *args, **options):
        if options["year"] and options["month"]:
            year, month = options["year"], options["month"]
        else:
            year, month = previous_month()

        label = french_month_year_label(year, month)
        self.stdout.write(f"Building leaderboard for {label}...")

        staff_emails = list(
            User.objects.filter(is_staff=True, is_active=True)
            .exclude(email="")
            .values_list("email", flat=True)
        )

        if not staff_emails:
            self.stdout.write(self.style.WARNING("No staff users with email found."))
            return

        msg = build_monthly_leaderboard_email(year, month)
        msg.subject = f"TEST EQUIPE RNB - {msg.subject}"
        for email in staff_emails:
            msg.to = [email]
            msg.send()
            self.stdout.write(f"  Sent to {email}")

        self.stdout.write(
            self.style.SUCCESS(
                f"Sent leaderboard email for {label} to {len(staff_emails)} staff user(s)."
            )
        )
