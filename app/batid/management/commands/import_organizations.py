import csv

from batid.models import Organization
from django.core.management.base import BaseCommand
from django.db.models import Q


class Command(BaseCommand):
    help = (
        "Import organizations from a CSV file (columns: editions, utilisateurs, "
        "email domain, nom orga, Acronyme, Commentaires, with 2 header lines). "
        "Rows without an org name are skipped. Existing organizations are matched "
        "by name or email domain and updated if a field changed. Each organization "
        "is saved individually to trigger user linking."
        "The data source and structure can be found on Grist: https://grist.numerique.gouv.fr/o/docs/1v4siTzHoLzK/RNB-organisations"
    )

    def add_arguments(self, parser):
        parser.add_argument("csv_path", type=str)

    def handle(self, *args, **options):
        created = updated = unchanged = 0
        seen_names = set()

        with open(options["csv_path"], newline="") as f:
            reader = csv.reader(f)
            rows = list(reader)[2:]  # skip the letter row and the header row

        for row in rows:
            name = row[3].strip()
            if not name:
                continue

            email_domain = row[2].strip() or None
            short_name = row[4].strip() or None

            if name in seen_names:
                self.stdout.write(
                    self.style.WARNING(
                        f"Duplicate name '{name}' in CSV, skipping row "
                        f"(ignored domain: {email_domain})"
                    )
                )
                continue
            seen_names.add(name)

            org = Organization.objects.filter(
                Q(name=name) | Q(email_domain=email_domain)
            ).first()

            if org is None:
                Organization.objects.create(
                    name=name, short_name=short_name, email_domain=email_domain
                )
                created += 1
            elif (org.name, org.short_name, org.email_domain) != (
                name,
                short_name,
                email_domain,
            ):
                org.name = name
                org.short_name = short_name
                org.email_domain = email_domain
                org.save()
                updated += 1
            else:
                unchanged += 1

        self.stdout.write(
            f"created: {created}, updated: {updated}, unchanged: {unchanged}"
        )
