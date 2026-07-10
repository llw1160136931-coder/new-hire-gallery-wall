from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Profile


@receiver(post_save, sender=User)
def ensure_profile(sender, instance, created, **kwargs):
    if created and not kwargs.get('raw'):
        role = Profile.Role.ADMIN if instance.is_staff else Profile.Role.STUDENT
        Profile.objects.get_or_create(
            user=instance,
            defaults={'name': instance.username, 'role': role},
        )
