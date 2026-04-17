from unittest import mock

from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase, override_settings

from batid.exceptions import INSEESireneAPIDown
from batid.services.insee_siren import extract_org_name, fetch_siren_data

FAKE_SIREN_RESPONSE = {
    "uniteLegale": {
        "siren": "130025265",
        "periodesUniteLegale": [
            {
                "dateDebut": "2020-01-01",
                "dateFin": None,
                "denominationUniteLegale": "DIRECTION INTERMINISTERIELLE DU NUMERIQUE",
            },
            {
                "dateDebut": "2010-01-01",
                "dateFin": "2019-12-31",
                "denominationUniteLegale": "DINSIC",
            },
        ],
    }
}


class FetchSirenDataTest(TestCase):
    """Tests for fetch_siren_data(siren).

    Inputs: SIREN string, mocked HTTP response.
    Expected: parsed dict on 200, None on 404, raises ImproperlyConfigured when key
    is missing, raises INSEESireneAPIDown on non-200/non-404 responses.
    """

    @override_settings(INSEE_SIRENE_API_KEY="test-key")
    @mock.patch("batid.services.insee_siren.requests.get")
    def test_returns_parsed_response_on_success(self, mock_get):
        """200 response -> returns parsed JSON dict."""
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = FAKE_SIREN_RESPONSE

        result = fetch_siren_data("130025265")

        self.assertEqual(result, FAKE_SIREN_RESPONSE)
        mock_get.assert_called_once_with(
            "https://api.insee.fr/api-sirene/3.11/siren/130025265",
            headers={
                "X-INSEE-Api-Key-Integration": "test-key",
                "Accept": "application/json",
            },
            timeout=5,
        )

    @override_settings(INSEE_SIRENE_API_KEY="test-key")
    @mock.patch("batid.services.insee_siren.requests.get")
    def test_returns_none_on_404(self, mock_get):
        """404 response (SIREN not found in SIRENE) -> returns None."""
        mock_get.return_value.status_code = 404

        result = fetch_siren_data("000000000")

        self.assertIsNone(result)

    @override_settings(INSEE_SIRENE_API_KEY="")
    def test_raises_when_api_key_not_configured(self):
        """Missing API key -> raises ImproperlyConfigured without making any HTTP call."""
        with self.assertRaises(ImproperlyConfigured):
            fetch_siren_data("130025265")

    @override_settings(INSEE_SIRENE_API_KEY="test-key")
    @mock.patch("batid.services.insee_siren.requests.get")
    def test_raises_when_api_returns_error(self, mock_get):
        """Non-200, non-404 status -> raises INSEESireneAPIDown."""
        mock_get.return_value.status_code = 500

        with self.assertRaises(INSEESireneAPIDown):
            fetch_siren_data("130025265")


class ExtractOrgNameTest(TestCase):
    """Tests for extract_org_name(unite_legale).

    Inputs: uniteLegale dict from INSEE API response.
    Expected: denominationUniteLegale from current period (dateFin=None),
    or empty string when no denomination exists. No personal name fallback.
    """

    def test_returns_denomination_from_current_period(self):
        """Returns denominationUniteLegale from the period where dateFin is None."""
        result = extract_org_name(FAKE_SIREN_RESPONSE["uniteLegale"])
        self.assertEqual(result, "DIRECTION INTERMINISTERIELLE DU NUMERIQUE")

    def test_returns_empty_string_when_no_denomination(self):
        """Returns empty string when current period has no denominationUniteLegale."""
        unite_legale = {
            "periodesUniteLegale": [{"dateDebut": "2020-01-01", "dateFin": None}]
        }
        self.assertEqual(extract_org_name(unite_legale), "")

    def test_returns_empty_string_when_no_periods(self):
        """Returns empty string when periodesUniteLegale is empty."""
        self.assertEqual(extract_org_name({"periodesUniteLegale": []}), "")
