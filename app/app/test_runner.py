from django.test.runner import DiscoverRunner
from django.test.utils import override_settings


class RNBTestRunner(DiscoverRunner):
    """
    Standard Django test runner, with two RNB specificities:
    - tests are allowed to use Django's native write functions (save, delete,
      bulk operations) on the Building model, which are locked everywhere else.
      See ForbiddenDjangoNativeFunction.
      Details: https://github.com/fab-geocommuns/RNB-coeur/pull/976
    - tests use a per-process in-memory cache instead of the shared Redis cache.
    """

    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        from batid.models import Building

        Building._native_functions_allowed = True

        # No dependency on the shared Redis, no state leaking from the dev
        # server or a previous run, and cache.clear() never flushes the dev cache.
        self._locmem_cache = override_settings(
            CACHES={
                "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
            }
        )
        self._locmem_cache.enable()

    def teardown_test_environment(self, **kwargs):
        self._locmem_cache.disable()
        super().teardown_test_environment(**kwargs)
