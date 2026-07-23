from django.test.runner import DiscoverRunner


class RNBTestRunner(DiscoverRunner):
    """
    Standard Django test runner, with one RNB specificity: tests are allowed
    to use Django's native write functions (save, delete, bulk operations)
    on the Building model, which are locked everywhere else.
    See ForbiddenDjangoNativeFunction.
    """

    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        from batid.models import Building

        Building._native_functions_allowed = True
