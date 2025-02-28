from typing import TypedDict

SplitCreatedBuilding = TypedDict(
    "SplitCreatedBuilding",
    {"status": str, "shape": str, "addresses_cle_interop": list[str]},
)
