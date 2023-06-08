from django.db.models.signals import post_save
from django.dispatch import receiver
from batid.models import BuildingADS, ADSAchievement, ADS, AsyncSignal, Building
from batid.services.signal import create_async_signal


@receiver(post_save, sender=BuildingADS)
def signal_bdg_ads(sender, instance, created, **kwargs):
    _calc_bdg_status_from_ads(instance.ads, instance.building)


@receiver(post_save, sender=ADSAchievement)
def signal_ads_achievement(sender, instance, created, **kwargs):
    _create_ads_achievement_clue_signal(instance.file_number)


@receiver(post_save, sender=ADS)
def signal_ads(sender, instance, created, **kwargs):
    # The current ADS has no achievement date. We signal so we might attach it.
    if instance.achieved_at is None:
        _create_ads_achievement_clue_signal(instance.file_number)

    # The ADS has been change, we might have to update the status of the buildings
    for op in instance.buildings_operations.all():
        _calc_bdg_status_from_ads(instance, op.building)


def _calc_bdg_status_from_ads(ads: ADS, bdg: Building) -> str:
    create_async_signal(
        type="calcStatusFromADS",
        building=bdg,
        origin=ads,
        creator=None,
    )


def _create_ads_achievement_clue_signal(file_number: str) -> AsyncSignal:
    return create_async_signal(
        type="adsAchievementClue",
        origin=f"ads:{file_number}",
        creator=None,
    )
