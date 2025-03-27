# abstract class, which will be extend by a specific class foreach django model
from abc import ABC
from datetime import datetime
from typing import List
from typing import Optional
from typing import Type

from django.db.models import Model

from batid.models import ADS as ADSModel


class ModelGear(ABC):
    model_cls = None

    def __init__(self, model: Type[Model]):
        if not isinstance(model, self.model_cls):
            raise ValueError(f"Expected a {self.model_cls.__name__}, got {type(model)}")

        self.model = model


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
