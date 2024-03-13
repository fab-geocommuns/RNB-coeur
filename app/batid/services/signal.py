import inspect
import sys
from typing import Protocol, runtime_checkable, Optional, Set, List
from batid.models import (
    Building,
    Organization,
    AsyncSignal as SignalModel,
    ADS,
    # BuildingStatus,
    ADSAchievement,
    BuildingADS,
)
from dateutil.utils import today
from django.contrib.auth.models import User
from django.contrib.gis.db import models
from app.celery import app
from batid.services.model_code import model_to_code, code_to_model, code_to_pk
from django.utils.timezone import now
from batid.services.models_gears import SignalGear  # , BuildingADSGear


def create_async_signal(
    type: str,
    origin,
    building: Building = None,
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


def _convert_user_to_org(user: User) -> Optional[Organization]:
    if user is None:
        return None

    if user.organizations.count() == 1:
        return user.organizations.first()

    return None


@runtime_checkable
class AsyncSignalHandlerProtocol(Protocol):
    def handle(self, signal: SignalGear) -> None: ...

    def should_handle(self, signal: SignalGear) -> bool: ...

    def get_name(self) -> str: ...


class AsyncSignalDispatcher:
    def __init__(self):
        self.signal = None
        self._handlers = set()

    def dispatch(self, signal: SignalModel):
        # We gear up the signal model to a SignalGear object
        self.signal = SignalGear(signal)

        # We check if the signal is already handled
        if self.signal.is_handled():
            return

        # We will build handlers which should handle this signal
        self._build_handlers()
        for handler in self._handlers:
            handler.handle()
            self.add_handle_results(handler.results)

        # Finally we set the signal as handled
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

    def add_handler(self, obs: AsyncSignalHandlerProtocol):
        self._handlers.add(obs)

    def _build_handlers(self):
        # list all classes in this module which implements SignalObserverProtocol
        # and add them to self._observers

        self._handlers = set()

        classes = inspect.getmembers(sys.modules[__name__], inspect.isclass)
        for name, cls in classes:
            if (
                issubclass(cls, AsyncSignalHandlerProtocol)
                and cls != AsyncSignalHandlerProtocol
            ):
                obs = cls(self.signal)
                if obs.should_handle():
                    self.add_handler(obs)


class AsyncSignalHandler:
    def __init__(self, signal: SignalGear):
        self.signal = signal
        self.results = []

    def get_name(self) -> str:
        return self.__class__.__name__

    def should_handle(self) -> bool:
        return False

    def handle(self) -> None:
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


# class CalcBdgStatusFromADSHandler(AsyncSignalHandler):
#     def handle(self) -> None:
#         ads = self.signal.get_origin()
#         op = BuildingADS.objects.filter(
#             ads=ads, building=self.signal.model.building
#         ).first()
#         opGear = BuildingADSGear(op)

#         previous_status = self.get_previous_status()
#         expected_status = opGear.get_expected_bdg_status()

#         self.install_status(previous_status, expected_status)

#     def install_status(
#         self, previous: List[BuildingStatus], expected: List[BuildingStatus]
#     ) -> None:
#         # All status are linked to the same building and the same ADS

#         # ###################
#         # Create missing expected status
#         for exp_status in expected:
#             exp_found = False

#             # We search
#             for prev_status in previous:
#                 if exp_status.type == prev_status.type:
#                     exp_found = True
#                     break

#             # If not found, we create
#             if not exp_found:
#                 exp_status.save()
#                 self.add_result(action="create", target=exp_status)

#         # #################
#         # Delete unexpected status
#         for prev_status in previous:
#             prev_found = False

#             # We search
#             for exp_status in expected:
#                 if exp_status.type == prev_status.type:
#                     prev_found = True
#                     break

#             # If not found, we create
#             if not prev_found:
#                 self.add_result(action="delete", target=prev_status)
#                 prev_status.delete()

#         pass

#     def get_previous_status(self) -> List[BuildingStatus]:
#         # all signals with same bdg and same origin, not this one
#         # get all results for status creation
#         # fetch those status
#         # return them

#         # Get all similar signals
#         same_signals = SignalModel.objects.filter(
#             building=self.signal.model.building,
#             origin=self.signal.model.origin,
#         ).exclude(id=self.signal.model.id)

#         # Get all BuildingStatus created by those signals
#         prev_results = []
#         for s_gear in [SignalGear(s) for s in same_signals]:
#             prev_results.extend(
#                 s_gear.get_results(
#                     {
#                         "handler": self.get_name(),
#                         "action": "create",
#                         "target_class": "BuildingStatus",
#                     }
#                 )
#             )

#         # Get all BuildingStatus objects
#         prev_status_ids = set()
#         for result in prev_results:
#             prev_status_ids.add(code_to_pk(result["target"]))

#         prev_status = BuildingStatus.objects.filter(id__in=prev_status_ids)

#         return list(prev_status)

#     def should_handle(self) -> bool:
#         return (
#             self.signal.model.type == "calcStatusFromADS"
#             and self.signal.origin_is_model()
#             and self.signal.get_origin_cls_name() == "ADS"
#         )


class ADSAchievementClueHandlerAsync(AsyncSignalHandler):
    def handle(self) -> None:
        _, file_number = self.signal.model.origin.split(":")

        # To build the achievement date, we need both the ADSAchievement and the ADS with the same file_number
        ads_achievement = ADSAchievement.objects.filter(file_number=file_number).first()
        if not isinstance(ads_achievement, ADSAchievement):
            return

        ads = (
            ADS.objects.filter(file_number=file_number)
            .exclude(achieved_at=ads_achievement.achieved_at)
            .first()
        )
        if not isinstance(ads, ADS):
            return

        # We update the ads with the achievement date
        ads.achieved_at = ads_achievement.achieved_at
        ads.save()

    def should_handle(self) -> bool:
        return self.signal.model.type == "adsAchievementClue"
