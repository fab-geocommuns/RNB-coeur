from batid.services.tchap import TchapLevel, notify_tech_or_log
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

# ponytail: QuerySet.update(is_superuser=True) and raw SQL bypass these signals and are
# not announced.


@receiver(pre_save, sender=User, dispatch_uid="batid_superuser_pre_save")
def detect_new_superuser(*, sender, instance, raw, update_fields, **kwargs) -> None:
    # Fixtures, and saves of other fields only (a login saves last_login): no query
    if raw or (update_fields is not None and "is_superuser" not in update_fields):
        instance._became_superuser = False
        return
    instance._became_superuser = instance.is_superuser and (
        instance.pk is None
        or not User.objects.filter(pk=instance.pk, is_superuser=True).exists()
    )


@receiver(post_save, sender=User, dispatch_uid="batid_superuser_post_save")
def announce_new_superuser(*, sender, instance, **kwargs) -> None:
    if not getattr(instance, "_became_superuser", False):
        return
    instance._became_superuser = False
    username = instance.username
    # Sent once the row is committed: an admin save runs in a transaction
    transaction.on_commit(
        lambda: notify_tech_or_log(
            level=TchapLevel.ALERT,
            title="Nouveau superutilisateur",
            details=[("Compte", username)],
        )
    )
