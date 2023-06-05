from typing import List

from batid.models import ADS as ADSModel
from batid.models import BuildingADS, Signal

from batid.services.signal import create_signal


def create_bdg_ads_signal(op: BuildingADS) -> Signal:
    signal_type = None
    if op.operation == "build":
        signal_type = "willBeBuilt"
    if op.operation == "demolish":
        signal_type = "willBeDemolished"
    if op.operation == "modify":
        signal_type = "willBeModified"

    if signal_type is None:
        raise ValueError("Unknown BuildingADS operation type")

    return create_signal(
        type=signal_type,
        building=op.building,
        origin=op.ads,
        creator=None,
        send_task=True,
    )


class ADS:
    def __init__(self, m: ADSModel):
        self.m = m

    def concerns_rnb_id(self, rnb_id: str) -> bool:
        return rnb_id in self.rnb_ids

    def get_op_by_rnbid(self, rnb_id: str):
        for b in self.m.buildings_operations.all():
            if b.building.rnb_id == rnb_id:
                return b
        return

    @property
    def rnb_ids(self) -> List[str]:
        return [op.building.rnb_id for op in self.m.buildings_operations.all()]
