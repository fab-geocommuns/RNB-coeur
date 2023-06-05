from pprint import pprint
from services.signal import fetch_signal, SignalDispatcher


def sandbox():
    s = fetch_signal(1)

    if s:
        d = SignalDispatcher(s)
        d.dispatch()

    pprint(s)


if __name__ == "__main__":
    sandbox()
