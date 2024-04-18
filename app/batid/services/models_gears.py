# abstract class, which will be extend by a specific class foreach django model
from abc import ABC
from datetime import datetime
from typing import List
from typing import Optional
from typing import Type

from django.contrib.auth.models import User as UserModel
from django.db.models import Model

from batid.models import ADS as ADSModel
from batid.models import AsyncSignal as SignalModel
from batid.services.model_code import code_to_cls_name
from batid.services.model_code import code_to_model
from batid.services.model_code import is_model_code


class ModelGear(ABC):
    model_cls = None

    def __init__(self, model: Type[Model]):
        if not isinstance(model, self.model_cls):
            raise ValueError(f"Expected a {self.model_cls.__name__}, got {type(model)}")

        self.model = model


class SignalGear(ModelGear):
    model_cls = SignalModel

    def is_handled(self) -> bool:
        return isinstance(self.model.handled_at, datetime)

    def origin_is_model(self) -> bool:
        return is_model_code(self.model.origin)

    def get_origin(self):
        if self.origin_is_model():
            return code_to_model(self.model.origin)

        return self.model.origin

    def get_origin_cls_name(self) -> Optional[str]:
        if self.origin_is_model():
            return code_to_cls_name(self.model.origin)

        return None

    def get_results(self, filters=Optional[dict]):
        results = []

        # If self.model.handle_result is None, return empty list
        if self.model.handle_result is None:
            return results

        # Set filters to dict so we can use .get()
        if filters is None:
            filters = {}

        for r in self.model.handle_result:
            if filters.get("handler") and r["handler"] != filters.get("handler"):
                continue

            if filters.get("action") and r["action"] != filters.get("action"):
                continue

            if filters.get("target") and r["target"] != filters.get("target"):
                continue

            if filters.get("target_class"):
                if code_to_cls_name(r["target"]) != filters.get("target_class"):
                    continue

            results.append(r)

        return results


# class BuildingADSGear(ModelGear):
#     model_cls = BuildingADSModel

#     def get_expected_bdg_status(self) -> List[BuildingStatusModel]:
#         results = []

#         if self.model.operation == "build":
#             return self._get_expected_build_status()
#         if self.model.operation == "modify":
#             return self._get_expected_modify_status()
#         if self.model.operation == "demolish":
#             return self._get_expected_demolish_status()

#         return results

# def _get_expected_modify_status(self) -> List[BuildingStatusModel]:
#     return []

# def _get_expected_demolish_status(self) -> List[BuildingStatusModel]:
#     results = []

#     if isinstance(self.model.ads.achieved_at, date):
#         results.append(
#             BuildingStatusModel(
#                 type="demolished",
#                 building=self.model.building,
#                 happened_at=self.model.ads.achieved_at,
#                 is_current=True,
#             )
#         )

#     return results

# def _get_expected_build_status(self) -> List[BuildingStatusModel]:
#     results = []

#     results.append(
#         BuildingStatusModel(
#             type="constructionProject",
#             building=self.model.building,
#             happened_at=self.model.ads.decided_at,
#             is_current=True,
#         )
#     )

#     if isinstance(self.model.ads.achieved_at, date):
#         results.append(
#             BuildingStatusModel(
#                 type="constructed",
#                 building=self.model.building,
#                 happened_at=self.model.ads.achieved_at,
#                 is_current=True,
#             )
#         )

#     return results


class ADSGear(ModelGear):
    model_cls = ADSModel

    def concerns_rnb_id(self, rnb_id: str) -> bool:
        return rnb_id in self.rnb_ids

    def get_op_by_rnbid(self, rnb_id: str):
        for b in self.model.buildings_operations.all():
            if b.building.rnb_id == rnb_id:
                return b
        return

    @property
    def rnb_ids(self) -> List[str]:
        return [op.building.rnb_id for op in self.model.buildings_operations.all()]
