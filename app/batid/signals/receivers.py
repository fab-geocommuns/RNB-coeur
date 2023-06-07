from django.db.models.signals import post_save
from django.dispatch import receiver
from batid.models import BuildingADS, ADSAchievement, ADS, Signal
from batid.services.signal import create_signal


@receiver(post_save, sender=BuildingADS)
def signal_bdg_ads(sender, instance, created, **kwargs):
    _create_bdg_ads_signal(instance)


@receiver(post_save, sender=ADSAchievement)
def signal_ads_achievement(sender, instance, created, **kwargs):
    _create_ads_achievement_clue_signal(instance.file_number)


@receiver(post_save, sender=ADS)
def signal_ads(sender, instance, created, **kwargs):
    if instance.achieved_at is None:
        # The current ADS has no achievement date. We signal it.
        _create_ads_achievement_clue_signal(instance.file_number)

    if instance.achieved_at is not None:
        _create_achieved_ads_signal(instance)


def _create_bdg_ads_signal(op: BuildingADS) -> Signal:
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
        type=signal_type, building=op.building, origin=op.ads, creator=None
    )


def _create_achieved_ads_signal(ads: ADS) -> Signal:
    return create_signal(type="adsAchieved", origin=ads)


def _create_ads_achievement_clue_signal(file_number: str) -> Signal:
    return create_signal(
        type="adsAchievementClue",
        origin=f"ads:{file_number}",
        creator=None,
    )
