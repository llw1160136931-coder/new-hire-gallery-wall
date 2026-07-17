import shutil
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction

from api.models import (
    AttendanceSession,
    ChunkedUpload,
    Course,
    Tag,
    TrainingCamp,
    Work,
    normalize_tag_name,
)

from .prepare_load_test import (
    LOADTEST_PREFIX,
    LOADTEST_TAG_PREFIX,
    require_loadtest_database,
)


class Command(BaseCommand):
    help = '只清理由固定 loadtest_ 前缀标记的压测数据。'

    def handle(self, *args, **options):
        require_loadtest_database()

        with transaction.atomic():
            test_camps = TrainingCamp.objects.filter(slug__startswith=LOADTEST_PREFIX)
            camp_ids = list(test_camps.values_list('id', flat=True))

            # Every destructive queryset is constrained by the immutable prefix.
            work_count, _ = Work.objects.filter(camp_id__in=camp_ids).delete()
            test_uploads = ChunkedUpload.objects.filter(camp_id__in=camp_ids)
            upload_count = test_uploads.count()
            for upload in test_uploads.iterator():
                shutil.rmtree(
                    Path(settings.WORK_UPLOAD_CHUNK_DIR) / str(upload.upload_id),
                    ignore_errors=True,
                )
                for field_name in ('file', 'protected_file'):
                    uploaded_file = getattr(upload, field_name, None)
                    if uploaded_file:
                        uploaded_file.delete(save=False)
            test_uploads.delete()
            attendance_count, _ = AttendanceSession.objects.filter(camp_id__in=camp_ids).delete()
            course_count, _ = Course.objects.filter(camp_id__in=camp_ids).delete()
            test_tags = Tag.objects.filter(
                normalized_name__startswith=normalize_tag_name(LOADTEST_TAG_PREFIX)
            )
            tag_count = test_tags.count()
            test_tags.delete()
            user_count, _ = User.objects.filter(username__startswith=LOADTEST_PREFIX).delete()
            camp_count, _ = test_camps.delete()

        self.stdout.write(self.style.SUCCESS('压测数据清理完成。'))
        self.stdout.write(
            '删除统计（包含级联记录）：'
            f'作品 {work_count}，上传 {upload_count}，签到 {attendance_count}，'
            f'课程 {course_count}，标签 {tag_count}，账号 {user_count}，'
            f'培训期 {camp_count}。'
        )
