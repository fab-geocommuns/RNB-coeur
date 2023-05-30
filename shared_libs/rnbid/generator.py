from nanoid import generate


def generate_id() -> str:
    id_len = 12
    # we remove 0, O and I from alphabet to avoid confusion when reading
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    return generate(size=id_len, alphabet=alphabet)
