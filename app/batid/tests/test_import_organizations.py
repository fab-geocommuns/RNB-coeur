import os
import tempfile
from io import StringIO

from batid.models import Organization, UserProfile
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase

CSV_HEADER = (
    "A,B,C,D,F,E\n"
    "editions,utilisateurs,email domain,nom orga,Acronyme,Commentaires\n"
)


class ImportOrganizationsTest(TestCase):
    """Tests for the import_organizations management command.

    The command reads a CSV (2 header lines, columns: editions, utilisateurs,
    email domain, nom orga, Acronyme, Commentaires), imports rows with a
    non-empty org name, matches existing orgs by name or email_domain to
    update them, and saves each org individually to trigger user linking.
    """

    def setUp(self):
        # The test DB is not empty: migration 0132 creates the "Équipe RNB"
        # org, so org counts are asserted relative to this baseline.
        self.initial_org_count = Organization.objects.count()

    def _write_csv(self, rows):
        """Write a CSV file with the standard 2 header lines plus the given
        data rows, return its path."""
        fd, path = tempfile.mkstemp(suffix=".csv")
        with os.fdopen(fd, "w") as f:
            f.write(CSV_HEADER)
            for row in rows:
                f.write(row + "\n")
        self.addCleanup(os.remove, path)
        return path

    def _call(self, csv_path):
        out = StringIO()
        call_command("import_organizations", csv_path, stdout=out)
        return out.getvalue()

    def test_creates_organization_from_row(self):
        """A row with a name creates an org with stripped name, short_name
        and email_domain."""
        path = self._write_csv(
            ["676,2,dgfip.finances.gouv.fr,Direction générale des Finances publiques , DGFiP,"]
        )

        self._call(path)

        org = Organization.objects.get(
            name="Direction générale des Finances publiques"
        )
        self.assertEqual(org.short_name, "DGFiP")
        self.assertEqual(org.email_domain, "dgfip.finances.gouv.fr")

    def test_skips_rows_without_name(self):
        """Rows with an empty org name are ignored: no org is created."""
        path = self._write_csv(
            [
                "357581,65,gmail.com,,,ex : pas d'organisation correspondante",
                "4587,6,free.fr,,,",
            ]
        )

        self._call(path)

        self.assertEqual(Organization.objects.count(), self.initial_org_count)

    def test_updates_org_matched_by_name(self):
        """An existing org with the same name but different short_name and
        email_domain gets both fields updated."""
        org = Organization.objects.create(name="Bordeaux Métropole")
        path = self._write_csv(
            ["55541,2,bordeaux-metropole.fr,Bordeaux Métropole,BM,"]
        )

        self._call(path)

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
        path = self._write_csv(["19041,1,grandlyon.com,Métropole de Lyon,,"])

        self._call(path)

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
        path = self._write_csv(["1483,2,grandest.fr,Région Grand Est,,"])

        self._call(path)

        org.refresh_from_db()
        self.assertEqual(org.updated_at, before)

    def test_duplicate_name_in_csv_first_row_wins(self):
        """Two CSV rows with the same org name and different domains: the
        first row creates the org, the second is skipped with a warning."""
        path = self._write_csv(
            [
                "40,1,pepcbfc.org,Pôle Énergie BFC,,",
                "2,1,pole-energie-bfc.fr,Pôle Énergie BFC,,",
            ]
        )

        output = self._call(path)

        org = Organization.objects.get(name="Pôle Énergie BFC")
        self.assertEqual(org.email_domain, "pepcbfc.org")
        self.assertIn("pole-energie-bfc.fr", output)

    def test_empty_csv_fields_stored_as_none(self):
        """A row without acronym stores short_name as None, not empty string."""
        path = self._write_csv(["713,3,brest-metropole.fr,Brest métropole,,"])

        self._call(path)

        org = Organization.objects.get(name="Brest métropole")
        self.assertIsNone(org.short_name)

    def test_import_links_users_by_email_domain(self):
        """Importing an org links existing users whose email domain matches
        (save() triggers link_organization_to_users)."""
        user = User.objects.create(
            username="agent", email="agent@brest-metropole.fr"
        )
        UserProfile.objects.create(user=user)
        path = self._write_csv(["713,3,brest-metropole.fr,Brest métropole,,"])

        self._call(path)

        org = Organization.objects.get(name="Brest métropole")
        self.assertTrue(org.user_profiles.filter(user=user).exists())

    def test_output_reports_counts(self):
        """The command output reports created, updated and unchanged counts."""
        Organization.objects.create(
            name="Région Grand Est", email_domain="grandest.fr"
        )
        Organization.objects.create(name="Bordeaux Métropole")
        path = self._write_csv(
            [
                "1483,2,grandest.fr,Région Grand Est,,",
                "55541,2,bordeaux-metropole.fr,Bordeaux Métropole,,",
                "19041,1,grandlyon.com,Métropole de Lyon,,",
                "357581,65,gmail.com,,,",
            ]
        )

        output = self._call(path)

        self.assertIn("created: 1", output)
        self.assertIn("updated: 1", output)
        self.assertIn("unchanged: 1", output)
