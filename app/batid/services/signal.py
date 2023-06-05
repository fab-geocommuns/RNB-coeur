import inspect
import sys
from typing import Protocol, runtime_checkable
from batid.models import Building, Organization, Signal
from django.contrib.auth.models import User
from django.contrib.gis.db import models
from app.celery import app


def create_signal(
    type: str,
    building: Building,
    origin,
    creator: User = None,
    send_task: bool = True,
) -> Signal:
    org = _convert_user_to_org(creator)

    signal_data = {
        "type": type,
        "building": building,
        "origin": _convert_signal_origin(origin),
        "creator_copy_id": creator.pk if creator else None,
        "creator_copy_fname": creator.first_name if creator else None,
        "creator_copy_lname": creator.last_name if creator else None,
        "creator_org_copy_id": org.pk if org else None,
        "creator_org_copy_name": org.name if org else None,
    }

    s = Signal.objects.create(**signal_data)
    if send_task:
        app.send_task("tasks.handle_signal", args=[s.pk])

    return s


def _convert_signal_origin(origin) -> str:
    if isinstance(origin, str):
        return origin
    elif isinstance(origin, models.Model):
        return f"{origin.__class__.__name__}:{origin.pk}"

    return ""


def _convert_user_to_org(user: User) -> Organization:
    if user is None:
        return None

    if user.organizations.count() == 1:
        return user.organizations.first()

    return None


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
    signals = Signal.objects.filter(id=pk)
    if signals.exists():
        return signals.first()

    return None
