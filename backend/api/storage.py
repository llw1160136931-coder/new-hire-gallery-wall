import os

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


@deconstructible
class ProtectedCourseStorage(FileSystemStorage):
    """Store course files outside MEDIA_ROOT so Nginx cannot expose them directly."""

    @property
    def location(self):
        return os.path.abspath(settings.COURSE_MATERIAL_ROOT)

    @property
    def base_url(self):
        return None


protected_course_storage = ProtectedCourseStorage()
