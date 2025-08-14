import math


def check(x, y, rel_tol=0.0, abs_tol=1e-6):
    if isinstance(x, list) and isinstance(y, list):
        return len(x) == len(y) and all(
            check(a, b, rel_tol, abs_tol) for a, b in zip(x, y)
        )
    elif isinstance(x, (int, float)) and isinstance(y, (int, float)):
        return math.isclose(x, y, rel_tol=rel_tol, abs_tol=abs_tol)
    else:
        return x == y
