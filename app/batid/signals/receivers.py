from typing import Optional

from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

from batid.models import ADS
from batid.models import ADSAchievement
from batid.models import AsyncSignal
from batid.services.signal import create_async_signal


@receiver(post_save, sender=ADSAchievement)
def signal_ads_achievement(sender, instance, created, **kwargs):
    # _async_create_ads_achievement_clue_signal(instance.file_number)
    pass


@receiver(post_save, sender=ADS)
def signal_ads(sender, instance, created, **kwargs):
    # The current ADS has no achievement date. We signal so we might attach it.
    # if instance.achieved_at is None:
    #     _async_create_ads_achievement_clue_signal(
    #         instance.file_number, instance.creator
    #     )
    pass


def _async_create_ads_achievement_clue_signal(
    file_number: str, creator: Optional[User]
) -> AsyncSignal:
    return create_async_signal(
        type="adsAchievementClue",
        origin=f"ads:{file_number}",
        creator=creator,
    )
