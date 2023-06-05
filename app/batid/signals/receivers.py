from django.db.models.signals import post_save
from django.dispatch import receiver
from batid.models import BuildingADS
from batid.services.ads import create_bdg_ads_signal


@receiver(post_save, sender=BuildingADS)
def signal_bdg_ads(sender, instance, created, **kwargs):
    create_bdg_ads_signal(instance)
