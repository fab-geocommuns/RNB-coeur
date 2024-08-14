from django.http import HttpRequest


def is_float(string: str) -> bool:
    try:
        float(string)
        return True
    except ValueError:
        return False


def root_url_from_request(request: HttpRequest) -> str:
    return f"{request.scheme}://{request.get_host()}"
