from nanoid import generate


def generate_id() -> str:
    # we remove 0, O and I from alphabet to avoid confusion when reading
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    return generate(size=12, alphabet=alphabet)


def clean_identifier(identifier: str) -> str:
    return identifier.replace(" ", "").replace("-", "").replace("_", "").upper()
