import datetime
import inspect
import sys
from typing import Protocol, Optional, runtime_checkable
from dataclasses import dataclass
from db import get_conn, dictfetchone


@dataclass
class Signal:
    id: int
    type: str
    building_id: int
    origin: str
    handled_at: Optional[datetime.datetime] = None
    handle_result: Optional[dict] = None
    created_at: Optional[datetime.datetime] = None
    creator_copy_id: Optional[int] = None
    creator_copy_fname: Optional[str] = None
    creator_copy_lname: Optional[str] = None
    creator_org_copy_id: Optional[int] = None
    creator_org_copy_name: Optional[str] = None


@runtime_checkable
class SignalObserverProtocol(Protocol):
    def handle(self, signal: Signal) -> None:
        ...

    def should_handle(self, signal: Signal) -> bool:
        ...


class SignalDispatcher:
    def __init__(self, signal: Signal):
        self.signal = signal
        self._observers = set()

    def dispatch(self):
        self._build_observers()
        for observer in self._observers:
            observer.handle(self.signal)

    def add_observer(self, obs: SignalObserverProtocol):
        self._observers.add(obs)

    def _build_observers(self):
        # list all classes in this module which implements SignalObserverProtocol
        # and add them to self._observers

        classes = inspect.getmembers(sys.modules[__name__], inspect.isclass)
        for name, cls in classes:
            if (
                issubclass(cls, SignalObserverProtocol)
                and cls != SignalObserverProtocol
            ):
                obs = cls()
                if obs.should_handle(self.signal):
                    self.add_observer(obs)


class WillBeBuiltSignalObserver:
    def handle(self, signal: Signal) -> None:
        print(f"Handling signal {signal.id} with {self.__class__.__name__}")
        pass

    def should_handle(self, signal: Signal) -> bool:
        return signal.type == "willBeBuilt"


class DACTSignalObserver:
    def handle(self, signal: Signal) -> None:
        print(f"Handling signal {signal.id} with {self.__class__.__name__}")
        pass

    def should_handle(self, signal: Signal) -> bool:
        return signal.type == "dact"


def fetch_signal(pk: int) -> Signal:
    q = "SELECT * FROM batid_signal WHERE id = %(pk)s"
    conn = get_conn()
    with conn.cursor() as cur:
        data = dictfetchone(cur, q, {"pk": pk})
        if data:
            return Signal(**data)

    return None
