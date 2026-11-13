from batid.tests.helpers import load_settings
from django.test import SimpleTestCase

from app.mfa_enforcement import MFAEnforcement


class MFAEnforcementSettingTest(SimpleTestCase):
    def test_absent_variable_defaults_to_required(self):
        """MFA_ENFORCEMENT not set: the settings load with REQUIRED, the
        strictest policy."""
        settings = load_settings({"MFA_ENFORCEMENT": None})

        self.assertEqual(settings["MFA_ENFORCEMENT"], MFAEnforcement.REQUIRED)

    def test_valid_values_are_accepted(self):
        """MFA_ENFORCEMENT set to OFF, OPTIONAL or REQUIRED: the settings load
        with the matching policy."""
        for value in ("OFF", "OPTIONAL", "REQUIRED"):
            with self.subTest(value=value):
                settings = load_settings({"MFA_ENFORCEMENT": value})
                self.assertEqual(settings["MFA_ENFORCEMENT"], MFAEnforcement(value))

    def test_invalid_value_fails_at_startup(self):
        """MFA_ENFORCEMENT set to a lower case value, to "False" (YAML reading
        an unquoted OFF) or to an unknown or empty value: evaluating the settings
        raises a ValueError, the app does not start."""
        for value in ("off", "False", "foo", ""):
            with self.subTest(value=value):
                with self.assertRaisesMessage(
                    ValueError, f"{value!r} is not a valid MFAEnforcement"
                ):
                    load_settings({"MFA_ENFORCEMENT": value})

    def test_totp_issuer_names_the_environment_outside_production(self):
        """DJANGO_ENV production: the authenticator app shows "RNB". Any other
        environment (staging): "RNB (staging)", so codes of two environments
        are not mixed up."""
        production = load_settings({"DJANGO_ENV": "production"})
        staging = load_settings({"DJANGO_ENV": "staging"})

        self.assertEqual(production["OTP_TOTP_ISSUER"], "RNB")
        self.assertEqual(staging["OTP_TOTP_ISSUER"], "RNB (staging)")
