import secrets
import string


def make_random_password(length: int) -> str:
    # https://docs.python.org/3/library/secrets.html#recipes-and-best-practices
    if length <= 0:
        raise ValueError("invalid password length")

    alphabet = string.ascii_letters + string.digits
    password = "".join(secrets.choice(alphabet) for i in range(length))
    return password
