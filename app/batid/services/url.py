from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


def add_params_to_url(url, params) -> str:
    # Merges params into url, replacing any existing value for the same key.
    parsed = urlparse(url)
    existing = [(k, v) for k, v in parse_qsl(parsed.query) if k not in params]
    new_query = urlencode(existing + list(params.items()))
    return urlunparse(parsed._replace(query=new_query))
