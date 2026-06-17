import csv
import io
from collections import Counter

import requests
from batid.models import Organization
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

EXPECTED_COLUMNS = ["email_domain", "org_name", "org_short_name", "comments"]


class Command(BaseCommand):
    help = (
        "Import organizations from a CSV downloaded at the given URL "
        "(columns: email_domain, org_name, org_short_name, comments). "
        "The whole file is rejected if the header or any row does not match "
        "this structure. The rows to import are displayed and a confirmation "
        "is asked before importing. Rows without an org name are skipped. "
        "Existing organizations are matched by name or email domain and "
        "updated if a field changed. Each organization is saved individually "
        "to trigger user linking. "
        "The data source and structure can be found on Grist: https://grist.numerique.gouv.fr/o/docs/1v4siTzHoLzK/RNB-organisations"
    )

    def add_arguments(self, parser):
        parser.add_argument("csv_url", type=str)

    def handle(self, *args, **options):
        rows = self._download_and_validate(options["csv_url"])

        to_import = [row for row in rows if row["org_name"].strip()]
        skipped = len(rows) - len(to_import)

        self.stdout.write(f"Organizations to import ({len(to_import)}):")
        for row in to_import:
            name = row["org_name"].strip()
            short_name = row["org_short_name"].strip()
            email_domain = row["email_domain"].strip()
            self.stdout.write(f"  {name} | {short_name or '-'} | {email_domain}")
        self.stdout.write(f"Rows without org name (skipped): {skipped}")

        if input("Proceed with import? [y/N] ").lower() not in ("y", "yes"):
            self.stdout.write("Import aborted.")
            return

        self._import(to_import)

    def _download_and_validate(self, url) -> list[dict]:
        """Download the CSV and reject the whole file unless the header
        matches EXPECTED_COLUMNS and every row has the same column count."""
        response = requests.get(url, timeout=30)
        response.raise_for_status()

        # Decode explicitly: requests falls back to Latin-1 when the server
        # does not declare a charset, which garbles the UTF-8 accents.
        content = response.content.decode("utf-8")
        reader = csv.DictReader(io.StringIO(content), restkey="_extra")

        if reader.fieldnames is None:
            raise CommandError("Downloaded file is empty")
        if reader.fieldnames != EXPECTED_COLUMNS:
            raise CommandError(
                f"Unexpected CSV header: {reader.fieldnames}, "
                f"expected: {EXPECTED_COLUMNS}"
            )

        rows = list(reader)
        for line_number, row in enumerate(rows, start=2):
            # DictReader flags column count mismatches: extra values land in
            # the restkey, missing ones are filled with None.
            if "_extra" in row or None in row.values():
                raise CommandError(
                    f"Line {line_number} does not have "
                    f"{len(EXPECTED_COLUMNS)} columns: {row}"
                )

        named_rows = [row for row in rows if row["org_name"].strip()]
        # Verify there is not duplicate in names
        self._reject_duplicates(
            "org name", [row["org_name"].strip() for row in named_rows]
        )
        # Verify there is no duplicate in email domains (ignoring empty ones, which are allowed to be shared) and reject the whole file if there is
        self._reject_duplicates(
            "email domain",
            [
                row["email_domain"].strip()
                for row in named_rows
                if row["email_domain"].strip()
            ],
        )

        return rows

    def _reject_duplicates(self, label, values):
        duplicates = [value for value, count in Counter(values).items() if count > 1]
        if duplicates:
            raise CommandError(f"Duplicate {label} in CSV: {duplicates}")

    @transaction.atomic
    def _import(self, rows):
        created = updated = unchanged = 0

        for row in rows:
            email_domain = row["email_domain"].strip() or None
            name = row["org_name"].strip()
            short_name = row["org_short_name"].strip() or None

            # Q(email_domain=None) would match any org without a domain,
            # so only match by domain when the row has one.
            lookup = Q(name=name)
            if email_domain:
                lookup |= Q(email_domain=email_domain)
            matches = list(Organization.objects.filter(lookup))

            if len(matches) > 1:
                raise CommandError(
                    f"Row (name: '{name}', email domain: '{email_domain}') "
                    f"matches several organizations: "
                    f"{[(o.pk, o.name, o.email_domain) for o in matches]}"
                )
            org = matches[0] if matches else None

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
