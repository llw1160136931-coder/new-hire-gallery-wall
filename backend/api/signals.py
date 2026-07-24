from django.contrib.auth.models import User
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Course, CourseResource, Profile, TalentProfileReport, Work, WorkImage


@receiver(post_save, sender=User)
def ensure_profile(sender, instance, created, **kwargs):
    if created and not kwargs.get('raw'):
        role = Profile.Role.ADMIN if instance.is_staff else Profile.Role.STUDENT
        Profile.objects.get_or_create(
            user=instance,
            defaults={'name': instance.username, 'role': role},
        )


@receiver(post_delete, sender=WorkImage)
def delete_work_image_file(sender, instance, **kwargs):
    if instance.image:
        instance.image.delete(save=False)


@receiver(post_delete, sender=Work)
def delete_work_files(sender, instance, **kwargs):
    for field_name in ('image', 'attachment', 'protected_attachment'):
        uploaded_file = getattr(instance, field_name, None)
        if uploaded_file:
            uploaded_file.delete(save=False)


@receiver(post_delete, sender=CourseResource)
def delete_course_resource_file(sender, instance, **kwargs):
    if instance.file:
        instance.file.delete(save=False)


@receiver(post_delete, sender=Course)
def delete_course_mind_map_file(sender, instance, **kwargs):
    if instance.mind_map:
        instance.mind_map.delete(save=False)


@receiver(post_delete, sender=TalentProfileReport)
def delete_talent_profile_report_file(sender, instance, **kwargs):
    if instance.file:
        instance.file.delete(save=False)
