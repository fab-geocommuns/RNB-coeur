from typing import Optional

from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

from batid.models import ADS
from batid.models import ADSAchievement
from batid.models import AsyncSignal
from batid.models import Building
from batid.models import BuildingADS
from batid.services.signal import create_async_signal

# from batid.services.models_gears import BuildingGear


# @receiver(post_save, sender=Building)
# def signal_bdg(sender, instance, created, **kwargs):
#     _sync_calc_missing_status(instance)


@receiver(post_save, sender=BuildingADS)
def signal_bdg_ads(sender, instance, created, **kwargs):
    _async_calc_bdg_status_from_ads(instance.ads, instance.building)


@receiver(post_save, sender=ADSAchievement)
def signal_ads_achievement(sender, instance, created, **kwargs):
    _async_create_ads_achievement_clue_signal(instance.file_number)


@receiver(post_save, sender=ADS)
def signal_ads(sender, instance, created, **kwargs):
    # The current ADS has no achievement date. We signal so we might attach it.
    if instance.achieved_at is None:
        _async_create_ads_achievement_clue_signal(
            instance.file_number, instance.creator
        )

    # The ADS has been change, we might have to update the status of the buildings
    for op in instance.buildings_operations.all():
        _async_calc_bdg_status_from_ads(instance, op.building)


# def _sync_calc_missing_status(bdg_model: Building):
#     bdg = BuildingGear(bdg_model)
#     missing_status = bdg.calc_missing_status()

#     for s in missing_status:
#         s.save()


def _async_calc_bdg_status_from_ads(ads: ADS, bdg: Building) -> str:
    create_async_signal(
        type="calcStatusFromADS", building=bdg, origin=ads, creator=ads.creator
    )


def _async_create_ads_achievement_clue_signal(
    file_number: str, creator: Optional[User]
) -> AsyncSignal:
    return create_async_signal(
        type="adsAchievementClue",
        origin=f"ads:{file_number}",
        creator=creator,
    )
