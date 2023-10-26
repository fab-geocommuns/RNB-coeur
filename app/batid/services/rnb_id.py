from nanoid import generate


def generate_rnb_id() -> str:
    # we remove 0, O, I, L and U from alphabet to avoid confusion when reading
    # as discussed here : https://github.com/fab-geocommuns/BatID/issues/24#issue-1597255114
    alphabet = "123456789ABCDEFGHJKMNPQRSTVWXYZ"
    return generate(size=12, alphabet=alphabet)


def clean_rnb_id(identifier: str) -> str:
    return identifier.replace(" ", "").replace("-", "").replace("_", "").upper()
