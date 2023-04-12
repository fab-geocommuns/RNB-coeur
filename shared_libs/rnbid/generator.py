from nanoid import generate


def generate_id() -> str:
    series = 3
    serie_len = 5

    # we remove 0, O and I from alphabet to avoid confusion when reading
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    id = generate(size=serie_len * series, alphabet=alphabet)

    chunks = _chunkstring(id, serie_len)

    return "-".join(chunks)


def _chunkstring(string: str, length: int) -> str:
    return (string[0 + i : length + i] for i in range(0, len(string), length))
