import inspect
import sys
from datetime import datetime
from typing import Protocol, runtime_checkable
from batid.models import Building, Organization, Signal as SignalModel, BuildingStatus
from dateutil.utils import today
from django.contrib.auth.models import User
from django.contrib.gis.db import models
from app.celery import app
from batid.services.model_code import model_to_code, code_to_model
from django.utils.timezone import now


def create_signal(
    type: str,
    building: Building,
    origin,
    creator: User = None,
    send_task: bool = True,
) -> SignalModel:
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

    s = SignalModel.objects.create(**signal_data)
    if send_task:
        app.send_task("batid.tasks.dispatch_signal", args=[s.pk])

    return s


def _convert_signal_origin(origin) -> str:
    if isinstance(origin, str):
        return origin
    elif isinstance(origin, models.Model):
        return model_to_code(origin)

    return ""


def _convert_user_to_org(user: User) -> Organization:
    if user is None:
        return None

    if user.organizations.count() == 1:
        return user.organizations.first()

    return None


class SignalGear:
    def __init__(self, signal: SignalModel):
        self.model = signal

    def origin_is_model(self) -> bool:
        return self.model.origin.startswith("model:")

    def origin_cls_name(self) -> str:
        if self.origin_is_model():
            return self.model.origin.split(":")[1]

        raise ValueError("Origin is not a model, it is a string")

    def get_origin(self):
        if self.origin_is_model():
            return code_to_model(self.model.origin)

        return self.model.origin

    def get_results(self, filters=None):
        results = []
        if filters is None:
            filters = {}

        for r in self.model.results:
            if filters.get("handler") and r["handler"] != filters.get("handler"):
                continue

            if filters.get("action") and r["action"] != filters.get("action"):
                continue

            if filters.get("target") and r["target"] != filters.get("target"):
                continue

            results.append(r)

        return results


@runtime_checkable
class SignalHandlerProtocol(Protocol):
    def handle(self, signal: SignalGear) -> list:
        ...

    def should_handle(self, signal: SignalGear) -> bool:
        ...

    def get_name(self) -> str:
        ...


class SignalDispatcher:
    def __init__(self):
        self.signal = None
        self._handlers = set()

    def dispatch(self, signal: SignalModel):
        # We gear up the signal model to a SignalGear object
        self.signal = SignalGear(signal)

        # build observers which should handle this signal
        self._build_handlers()
        for handler in self._handlers:
            result = handler.handle(self.signal)
            self.add_handle_results(result)

        self.mark_signal_as_handled()

    def add_handle_results(self, results: list):
        # First we make sure the model has a list as handle_result
        if not isinstance(self.signal.model.handle_result, list):
            self.signal.model.handle_result = []

        if results is None:
            return

        if isinstance(results, list):
            self.signal.model.handle_result.extend(results)
            return

        raise ValueError("Handler results must be a list")

    def mark_signal_as_handled(self):
        self.signal.model.handled_at = now()
        self.signal.model.save()

    def add_handler(self, obs: SignalHandlerProtocol):
        self._handlers.add(obs)

    def _build_handlers(self):
        # list all classes in this module which implements SignalObserverProtocol
        # and add them to self._observers

        self._handlers = set()

        classes = inspect.getmembers(sys.modules[__name__], inspect.isclass)
        for name, cls in classes:
            if issubclass(cls, SignalHandlerProtocol) and cls != SignalHandlerProtocol:
                obs = cls()
                if obs.should_handle(self.signal):
                    self.add_handler(obs)


class SignalHandler:
    def __init__(self):
        self.results = []

    def get_name(self) -> str:
        return self.__class__.__name__

    def should_handle(self, signal: SignalGear) -> bool:
        return False

    def handle(self, signal: SignalGear) -> list:
        raise NotImplementedError

    def add_result(self, action: str = None, target=None) -> None:
        if isinstance(target, models.Model):
            target_str = model_to_code(target)
        if isinstance(target, str):
            target_str = target

        result = {
            "handler": self.get_name(),
            "action": action,
            "target": target_str,
        }

        self.results.append(result)


class ADSWillBeBuiltSignalHandler(SignalHandler):
    def handle(self, signal: SignalGear) -> list:
        s = BuildingStatus.objects.create(
            type="constructionProject",
            building=signal.model.building,
            happened_at=signal.get_origin().decision_date,
            is_current=True,
        )
        self.add_result(action="create", target=s)

        return self.results

    def should_handle(self, signal: SignalGear) -> bool:
        if (
            signal.origin_is_model()
            and signal.origin_cls_name() == "ADS"
            and signal.model.type == "willBeBuilt"
        ):
            return True

        return False


class DACTSignalHandler(SignalHandler):
    def handle(self, signal: SignalGear) -> list:
        print(f"Handling signal {signal.id} with {self.__class__.__name__}")
        pass

    def should_handle(self, signal: SignalGear) -> bool:
        return signal.model.type == "dact"
