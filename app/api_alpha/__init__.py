# this is a temporary hack until unittest integration with VS Code is fixed
# see https://github.com/Microsoft/vscode-python/issues/73#issuecomment-1334196634
from django.conf import settings

if not settings.configured:
    import unittest
    import os
    from django import setup

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.settings")
    setup()

    from django.test.utils import (
        setup_test_environment,
        teardown_test_environment,
        teardown_databases,
        setup_databases,
    )

    VERBOSITY = 1
    INTERACTIVE = False

    def djangoSetUpTestRun(self):
        setup_test_environment()
        self._django_db_config = setup_databases(VERBOSITY, INTERACTIVE)

    def djangoTearDownTestRun(self):
        teardown_databases(self._django_db_config, VERBOSITY)
        teardown_test_environment()

    setattr(unittest.TestResult, "startTestRun", djangoSetUpTestRun)
    setattr(unittest.TestResult, "stopTestRun", djangoTearDownTestRun)
