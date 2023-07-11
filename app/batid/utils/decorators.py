import functools
from time import perf_counter


def show_duration(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = perf_counter()
        res = func(*args, **kwargs)
        end = perf_counter()
        print(f"{func.__name__ } - duration: {end - start} seconds")
        return res

    return wrapper
