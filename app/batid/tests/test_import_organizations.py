from io import StringIO
from unittest import mock

from batid.models import Organization, UserProfile
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

CSV_HEADER = "email_domain,org_name,org_short_name,comments\n"

CSV_URL = "https://example.com/rnb_organisations.csv"


class ImportOrganizationsTest(TestCase):
    """Tests for the import_organizations management command.

    The command downloads a CSV from a mandatory URL (columns: email_domain,
    org_name, org_short_name, comments), rejects the whole file if the header
    does not match, displays the rows to import and asks for confirmation.
    It then imports rows with a non-empty org name, matching existing orgs by
    name or email_domain to update them, and saves each org individually to
    trigger user linking.
    """

    def setUp(self):
        # The test DB is not empty: migration 0132 creates the "Équipe RNB"
        # org, so org counts are asserted relative to this baseline.
        self.initial_org_count = Organization.objects.count()

    def _csv(self, rows):
        return CSV_HEADER + "".join(row + "\n" for row in rows)

    def _call(self, csv_content, confirm="y"):
        """Run the command against a mocked download of csv_content,
        answering the confirmation prompt with `confirm`.

        The mocked response mimics a server that does not declare a charset:
        `.content` holds the UTF-8 bytes while `.text` is the mojibake
        Latin-1 guess of requests — the command must decode from content.
        """
        out = StringIO()
        raw = csv_content.encode("utf-8")
        with mock.patch(
            "batid.management.commands.import_organizations.requests.get"
        ) as mock_get, mock.patch("builtins.input", return_value=confirm):
            mock_get.return_value = mock.Mock(
                content=raw, text=raw.decode("latin-1"), status_code=200
            )
            call_command("import_organizations", CSV_URL, stdout=out)
        return out.getvalue()

    # --- CSV structure validation ---

    def test_rejects_wrong_column_names(self):
        """A header with an unexpected column name raises CommandError and
        nothing is imported, even if data rows are valid."""
        content = "domain,org_name,org_short_name,comments\n" + (
            "bordeaux-metropole.fr,Bordeaux Métropole,,\n"
        )

        with self.assertRaises(CommandError):
            self._call(content)

        self.assertEqual(Organization.objects.count(), self.initial_org_count)

    def test_rejects_wrong_column_count(self):
        """A header with a missing column raises CommandError and nothing
        is imported."""
        content = "email_domain,org_name,org_short_name\n" + (
            "bordeaux-metropole.fr,Bordeaux Métropole,\n"
        )

        with self.assertRaises(CommandError):
            self._call(content)

        self.assertEqual(Organization.objects.count(), self.initial_org_count)

    def test_rejects_malformed_data_row(self):
        """A data row whose column count differs from the header (e.g. an
        unquoted comma) raises CommandError and nothing is imported."""
        content = self._csv(
            [
                "bordeaux-metropole.fr,Bordeaux Métropole,,",
                "grandlyon.com,Métropole de Lyon, fondée en 1969,ML,",
            ]
        )

        with self.assertRaises(CommandError):
            self._call(content)

        self.assertEqual(Organization.objects.count(), self.initial_org_count)

    def test_rejects_non_csv_content(self):
        """Non-CSV content (e.g. an HTML error page) raises CommandError
        and nothing is imported."""
        content = "<!DOCTYPE html>\n<html><body>Not found</body></html>\n"

        with self.assertRaises(CommandError):
            self._call(content)

        self.assertEqual(Organization.objects.count(), self.initial_org_count)

    # --- Confirmation ---

    def test_displays_rows_before_import(self):
        """The command output lists the organizations to import (name and
        email domain) before asking for confirmation."""
        content = self._csv(["bordeaux-metropole.fr,Bordeaux Métropole,BM,"])

        output = self._call(content)

        self.assertIn("Bordeaux Métropole", output)
        self.assertIn("bordeaux-metropole.fr", output)

    def test_aborts_when_not_confirmed(self):
        """Answering 'n' at the confirmation prompt imports nothing."""
        content = self._csv(["bordeaux-metropole.fr,Bordeaux Métropole,,"])

        output = self._call(content, confirm="n")

        self.assertEqual(Organization.objects.count(), self.initial_org_count)
        self.assertNotIn("created", output)

    # --- Import logic ---

    def test_creates_organization_from_row(self):
        """A row with a name creates an org with stripped name, short_name
        and email_domain."""
        content = self._csv(
            ["dgfip.finances.gouv.fr,Direction générale des Finances publiques , DGFiP,"]
        )

        self._call(content)

        org = Organization.objects.get(
            name="Direction générale des Finances publiques"
        )
        self.assertEqual(org.short_name, "DGFiP")
        self.assertEqual(org.email_domain, "dgfip.finances.gouv.fr")

    def test_skips_rows_without_name(self):
        """Rows with an empty org name are ignored: no org is created."""
        content = self._csv(
            [
                "gmail.com,,,ex : pas d'organisation correspondante",
                "free.fr,,,",
            ]
        )

        self._call(content)

        self.assertEqual(Organization.objects.count(), self.initial_org_count)

    def test_updates_org_matched_by_name(self):
        """An existing org with the same name but different short_name and
        email_domain gets both fields updated."""
        org = Organization.objects.create(name="Bordeaux Métropole")
        content = self._csv(["bordeaux-metropole.fr,Bordeaux Métropole,BM,"])

        self._call(content)

        org.refresh_from_db()
        self.assertEqual(org.email_domain, "bordeaux-metropole.fr")
        self.assertEqual(org.short_name, "BM")
        self.assertEqual(Organization.objects.count(), self.initial_org_count + 1)

    def test_updates_org_matched_by_email_domain(self):
        """An existing org with the same email_domain but a different name
        gets its name updated, no new org is created."""
        org = Organization.objects.create(
            name="Lyon", email_domain="grandlyon.com"
        )
        content = self._csv(["grandlyon.com,Métropole de Lyon,,"])

        self._call(content)

        org.refresh_from_db()
        self.assertEqual(org.name, "Métropole de Lyon")
        self.assertEqual(Organization.objects.count(), self.initial_org_count + 1)

    def test_unchanged_org_is_not_saved(self):
        """An org already identical to its CSV row is not saved again:
        updated_at (auto_now) stays unchanged."""
        org = Organization.objects.create(
            name="Région Grand Est", email_domain="grandest.fr"
        )
        before = Organization.objects.get(pk=org.pk).updated_at
        content = self._csv(["grandest.fr,Région Grand Est,,"])

        self._call(content)

        org.refresh_from_db()
        self.assertEqual(org.updated_at, before)

    def test_rejects_duplicate_org_name(self):
        """Two rows with the same org name (and different domains) raise
        CommandError and nothing is imported."""
        content = self._csv(
            [
                "pepcbfc.org,Pôle Énergie BFC,,",
                "pole-energie-bfc.fr,Pôle Énergie BFC,,",
            ]
        )

        with self.assertRaises(CommandError):
            self._call(content)

        self.assertEqual(Organization.objects.count(), self.initial_org_count)

    def test_rejects_duplicate_email_domain(self):
        """Two named rows with the same email domain raise CommandError and
        nothing is imported."""
        content = self._csv(
            [
                "grandlyon.com,Métropole de Lyon,,",
                "grandlyon.com,Ville de Lyon,,",
            ]
        )

        with self.assertRaises(CommandError):
            self._call(content)

        self.assertEqual(Organization.objects.count(), self.initial_org_count)

    def test_repeated_empty_domains_are_not_duplicates(self):
        """Two named rows without email domain are not duplicates: both
        orgs are created, each with email_domain None."""
        content = self._csv(
            [
                ",Org Sans Domaine A,,",
                ",Org Sans Domaine B,,",
            ]
        )

        self._call(content)

        self.assertEqual(
            Organization.objects.count(), self.initial_org_count + 2
        )
        org_b = Organization.objects.get(name="Org Sans Domaine B")
        self.assertIsNone(org_b.email_domain)

    def test_empty_csv_fields_stored_as_none(self):
        """A row without acronym stores short_name as None, not empty string."""
        content = self._csv(["brest-metropole.fr,Brest métropole,,"])

        self._call(content)

        org = Organization.objects.get(name="Brest métropole")
        self.assertIsNone(org.short_name)

    def test_import_links_users_by_email_domain(self):
        """Importing an org links existing users whose email domain matches
        (save() triggers link_organization_to_users)."""
        user = User.objects.create(
            username="agent", email="agent@brest-metropole.fr"
        )
        UserProfile.objects.create(user=user)
        content = self._csv(["brest-metropole.fr,Brest métropole,,"])

        self._call(content)

        org = Organization.objects.get(name="Brest métropole")
        self.assertTrue(org.user_profiles.filter(user=user).exists())

    def test_output_reports_counts(self):
        """The command output reports created, updated and unchanged counts."""
        Organization.objects.create(
            name="Région Grand Est", email_domain="grandest.fr"
        )
        Organization.objects.create(name="Bordeaux Métropole")
        content = self._csv(
            [
                "grandest.fr,Région Grand Est,,",
                "bordeaux-metropole.fr,Bordeaux Métropole,,",
                "grandlyon.com,Métropole de Lyon,,",
                "gmail.com,,,",
            ]
        )

        output = self._call(content)

        self.assertIn("created: 1", output)
        self.assertIn("updated: 1", output)
        self.assertIn("unchanged: 1", output)
