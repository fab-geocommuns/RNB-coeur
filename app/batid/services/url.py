from urllib.parse import parse_qsl
from urllib.parse import urlencode
from urllib.parse import urlparse
from urllib.parse import urlunparse


def add_params_to_url(url, params) -> str:
    # Merges params into url, appending with & when a query string already exists.
    parsed = urlparse(url)
    existing = parse_qsl(parsed.query)
    new_query = urlencode(existing + list(params.items()))
    return urlunparse(parsed._replace(query=new_query))
