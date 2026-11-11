from datetime import date
from unittest import mock

import requests
from batid.services.imports.import_plots import (
    ETALAB_CADASTRE_URL,
    etalab_recent_release_date,
    pick_release_date,
)
from django.test import SimpleTestCase

RELEASE_DATES = [
    date(2026, 9, 1),
    date(2025, 9, 1),
    date(2026, 3, 1),
    date(2025, 12, 1),
    date(2026, 6, 1),
]

ETALAB_INDEX_HTML = """
<table>
  <tr><td><a href="../">../</a></td></tr>
  <tr><td><a href="/data/etalab-cadastre/2025-12-01/">2025-12-01/</a></td><td></td></tr>
  <tr><td><a href="/data/etalab-cadastre/2026-09-01/">2026-09-01/</a></td><td></td></tr>
  <tr><td><a href="/data/etalab-cadastre/2026-06-01/">2026-06-01/</a></td><td></td></tr>
</table>
"""


class PickReleaseDateTestCase(SimpleTestCase):
    def test_latest_release_before_date(self):
        """
        Input: unsorted releases, before 2026-05-24.
        Expected: "2026-03-01", the latest release before that date.
        """
        release = pick_release_date(
            release_dates=RELEASE_DATES, before=date(2026, 5, 24)
        )
        self.assertEqual(release, "2026-03-01")

    def test_release_day_is_excluded(self):
        """
        Input: unsorted releases, before 2026-06-01 (a release day).
        Expected: "2026-03-01", since the bound is strictly before.
        """
        release = pick_release_date(
            release_dates=RELEASE_DATES, before=date(2026, 6, 1)
        )
        self.assertEqual(release, "2026-03-01")

    def test_no_bound_returns_latest_release(self):
        """
        Input: unsorted releases, before=None.
        Expected: "2026-09-01", the latest release.
        """
        release = pick_release_date(release_dates=RELEASE_DATES, before=None)
        self.assertEqual(release, "2026-09-01")

    def test_bound_earlier_than_every_release_raises(self):
        """
        Input: unsorted releases, before 2025-01-01 (earlier than all of them).
        Expected: ValueError.
        """
        with self.assertRaises(ValueError):
            pick_release_date(release_dates=RELEASE_DATES, before=date(2025, 1, 1))

    def test_empty_release_list_raises(self):
        """
        Input: empty release list, before=None.
        Expected: ValueError.
        """
        with self.assertRaises(ValueError):
            pick_release_date(release_dates=[], before=None)


class EtalabRecentReleaseDateTestCase(SimpleTestCase):
    @mock.patch("batid.services.imports.import_plots.requests.get")
    def test_reads_releases_from_etalab_index(self, get_mock):
        """
        Input: Etalab index HTML with a "../" link and 3 dated release links.
        Expected: "2026-09-01", the latest one; the index URL is fetched with a timeout.
        """
        get_mock.return_value.text = ETALAB_INDEX_HTML

        self.assertEqual(etalab_recent_release_date(), "2026-09-01")

        get_mock.assert_called_once()
        self.assertEqual(get_mock.call_args.args, (ETALAB_CADASTRE_URL,))
        self.assertIn("timeout", get_mock.call_args.kwargs)

    @mock.patch("batid.services.imports.import_plots.requests.get")
    def test_index_without_release_raises(self, get_mock):
        """
        Input: Etalab index HTML with only the "../" link.
        Expected: ValueError.
        """
        get_mock.return_value.text = '<a href="../">../</a>'

        with self.assertRaises(ValueError):
            etalab_recent_release_date()

    @mock.patch("batid.services.imports.import_plots.requests.get")
    def test_http_error_propagates(self, get_mock):
        """
        Input: the Etalab index answers with an HTTP error.
        Expected: requests.HTTPError is raised to the caller.
        """
        get_mock.return_value.raise_for_status.side_effect = requests.HTTPError("503")

        with self.assertRaises(requests.HTTPError):
            etalab_recent_release_date()
