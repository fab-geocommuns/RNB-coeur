from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from batid.models import Address
from django.db.models import QuerySet


@dataclass(frozen=True)
class BanAddressMatch:
    """The local addresses matching a BAN address identifier (given by the user or
    by the BAN geocoder), and the identifier they were found with."""

    addresses: QuerySet
    found_with: Literal["ban_id", "cle_interop"]


def resolve_ban_address(cle_interop: str, ban_id: UUID | None) -> BanAddressMatch:
    """
    Find the local addresses matching an address as the BAN currently describes it:
    its interop key, and its BAN ID when the BAN gives one.

    `Address.ban_id` is only filled for the cities with reliable BAN IDs:
    - if a local address holds the BAN ID, it is this address;
    - if no local address holds it, the local addresses with this key and no BAN ID
      match. One with the same key but another BAN ID is another address (the key
      has been reassigned);
    - if the BAN gives no BAN ID, nothing shows the key has been reassigned: the
      local addresses with this key match, whether they hold a BAN ID or not.
    """
    if ban_id is not None:
        by_ban_id = Address.objects.filter(ban_id=ban_id)
        if by_ban_id.exists():
            return BanAddressMatch(addresses=by_ban_id, found_with="ban_id")

    by_key = Address.objects.filter(cle_interop__iexact=cle_interop)
    if ban_id is not None:
        by_key = by_key.filter(ban_id__isnull=True)
    return BanAddressMatch(addresses=by_key, found_with="cle_interop")
