from django.core import signing
from django.http import HttpResponseForbidden
from django.views.decorators.http import require_GET


@require_GET
def test_error(request):
    """
    Test endpoint to deliberately raise an error for Sentry capture testing.
    Access this endpoint with a valid signed token to trigger a test error.

    To generate a valid token, run this in Django shell (python manage.py shell):

    from django.core import signing
    token = signing.dumps('error-test', salt='error-test')
    print(f'Your token: {token}')

    Then access the endpoint with: /__test__/error/?token=<your_token>
    """
    token = request.GET.get("token")
    if not token:
        return HttpResponseForbidden("Missing token")

    try:
        # Verify the token is valid and contains our expected value
        value = signing.loads(token, salt="error-test")
        if value != "error-test":
            return HttpResponseForbidden("Invalid token")
    except signing.BadSignature:
        return HttpResponseForbidden("Invalid token")

    raise Exception("This is a test error")
