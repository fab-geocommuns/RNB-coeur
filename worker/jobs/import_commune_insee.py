def retrieve_token(consumer_key: str, consumer_secret: str) -> str:
    """Retrieves Token based on client secrets"""
    encodedData = base64.b64encode(
        bytes(f"{consumer_key}:{consumer_secret}", "ISO-8859-1")
    ).decode("ascii")

    headers = {
        "Authorization": f"Basic {encodedData}",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    data = {"grant_type": "client_credentials"}
    url = os.environ.get("INSEE_TOKEN_URL")
    response = requests.post(url, headers=headers, data=data, verify=False)

    if response.status_code == 200:
        return response.json()["access_token"]
    else:
        raise ValueError(response.status_code, response.text)

