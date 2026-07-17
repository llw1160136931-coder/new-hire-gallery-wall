import hashlib
import json
import shutil
from datetime import timedelta
from io import StringIO
from pathlib import Path
from unittest import mock

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import TestCase, override_settings
from django.utils import timezone

from .models import ChunkedUpload, Like, TrainingCamp, Vote, Work


TEST_DIR = Path(__file__).resolve().parent / '.test_verify_load_test'
TEST_MEDIA_DIR = TEST_DIR / 'media'
TEST_CHUNK_DIR = TEST_DIR / 'chunks'


@override_settings(
    PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],
    MEDIA_ROOT=TEST_MEDIA_DIR,
    WORK_UPLOAD_CHUNK_DIR=TEST_CHUNK_DIR,
)
class VerifyLoadTestCommandTests(TestCase):
    def setUp(self):
        shutil.rmtree(TEST_DIR, ignore_errors=True)
        TEST_DIR.mkdir(parents=True, exist_ok=True)
        self.report_path = TEST_DIR / 'verification.json'

    def tearDown(self):
        shutil.rmtree(TEST_DIR, ignore_errors=True)

    def create_valid_loadtest_data(self):
        now = timezone.now()
        today = timezone.localdate()
        camp = TrainingCamp.objects.create(
            name='Load test verification',
            slug='loadtest_verify',
            start_date=today - timedelta(days=1),
            end_date=today + timedelta(days=1),
            submission_starts_at=now - timedelta(days=1),
            submission_ends_at=now + timedelta(days=1),
            voting_starts_at=now - timedelta(days=1),
            voting_ends_at=now + timedelta(days=1),
            is_active=True,
        )
        user = User.objects.create_user(
            username='loadtest_verify_user',
            password='not-exported-in-report',
        )
        target = Work.objects.create(
            camp=camp,
            author=user,
            title='[LOADTEST] interaction target',
            work_type=Work.WorkType.TRAINING,
            media_type=Work.MediaType.LINK,
            link='https://example.com/loadtest',
            description='target',
            status=Work.Status.APPROVED,
        )
        Like.objects.create(user=user, work=target)
        Vote.objects.create(user=user, work=target)

        image_work = Work.objects.create(
            camp=camp,
            author=user,
            title='loadtest-run-images-user-1',
            work_type=Work.WorkType.AI,
            media_type=Work.MediaType.IMAGE,
            description='image',
            status=Work.Status.APPROVED,
        )
        image_work.image.save(
            'loadtest-verification.jpg',
            ContentFile(b'non-empty-image-fixture'),
            save=True,
        )

        video_payload = b'\x00\x00\x00\x18ftypisom' + (b'video' * 64)
        digest = hashlib.sha256(video_payload).hexdigest()
        upload = ChunkedUpload.objects.create(
            camp=camp,
            owner=user,
            file_name='loadtest-verification.mp4',
            content_type='video/mp4',
            media_type=Work.MediaType.VIDEO,
            total_size=len(video_payload),
            total_chunks=1,
            uploaded_chunks=[0],
            expected_sha256=digest,
            sha256=digest,
            status=ChunkedUpload.Status.CONSUMED,
            expires_at=now + timedelta(days=1),
            consumed_at=now,
        )
        upload.file.save(
            'loadtest-verification.mp4',
            ContentFile(video_payload),
            save=True,
        )
        video_work = Work.objects.create(
            camp=camp,
            author=user,
            title='loadtest-run-video-user-1',
            work_type=Work.WorkType.AI,
            media_type=Work.MediaType.VIDEO,
            attachment=upload.file.name,
            original_filename=upload.file_name,
            content_type=upload.content_type,
            file_size=upload.total_size,
            description='video',
            status=Work.Status.APPROVED,
        )
        return camp, user, target, image_work, video_work

    def call_command_in_database(self, database_name, **kwargs):
        with mock.patch.dict(connection.settings_dict, {'NAME': database_name}):
            return call_command(
                'verify_load_test',
                output=self.report_path,
                stdout=StringIO(),
                **kwargs,
            )

    @staticmethod
    def minimum_options():
        return {
            'expected_users': 1,
            'expected_seed_targets': 1,
            'min_likes': 1,
            'min_votes': 1,
            'min_uploaded_image_works': 1,
            'min_uploaded_video_works': 1,
        }

    def test_pass_report_checks_relations_files_hash_and_performs_no_db_writes(self):
        self.create_valid_loadtest_data()
        before = {
            'users': User.objects.count(),
            'works': Work.objects.count(),
            'likes': Like.objects.count(),
            'votes': Vote.objects.count(),
            'uploads': ChunkedUpload.objects.count(),
        }

        self.call_command_in_database(
            'new_hire_gallery_loadtest',
            **self.minimum_options(),
        )

        after = {
            'users': User.objects.count(),
            'works': Work.objects.count(),
            'likes': Like.objects.count(),
            'votes': Vote.objects.count(),
            'uploads': ChunkedUpload.objects.count(),
        }
        self.assertEqual(after, before)
        report = json.loads(self.report_path.read_text(encoding='utf-8'))
        self.assertEqual(report['status'], 'PASS')
        self.assertEqual(report['summary']['issue_count'], 0)
        self.assertEqual(
            report['checks']['uploaded_video_sha256']['checked_video_hashes'],
            1,
        )
        self.assertFalse(report['database_safety']['database_writes_performed'])
        serialized = json.dumps(report, ensure_ascii=False)
        self.assertNotIn(str(TEST_DIR.resolve()), serialized)
        self.assertNotIn('not-exported-in-report', serialized)

    def test_fail_report_for_missing_file_and_unfinished_upload(self):
        camp, user, *_, video_work = self.create_valid_loadtest_data()
        Work.objects.create(
            camp=camp,
            author=user,
            title='loadtest-missing-images-user-1',
            work_type=Work.WorkType.AI,
            media_type=Work.MediaType.IMAGE,
            image='works/does-not-exist.jpg',
            description='missing',
            status=Work.Status.APPROVED,
        )
        pending = ChunkedUpload.objects.create(
            camp=camp,
            owner=user,
            file_name='pending.mp4',
            content_type='video/mp4',
            media_type=Work.MediaType.VIDEO,
            total_size=10,
            total_chunks=1,
            uploaded_chunks=[],
            status=ChunkedUpload.Status.UPLOADING,
            expires_at=timezone.now() + timedelta(days=1),
        )
        (TEST_CHUNK_DIR / str(pending.upload_id)).mkdir(parents=True)
        with video_work.attachment.storage.open(video_work.attachment.name, 'wb') as target:
            target.write(b'tampered-video')

        with self.assertRaisesMessage(CommandError, '验收未通过'):
            self.call_command_in_database(
                'new_hire_gallery_loadtest',
                **self.minimum_options(),
            )

        report = json.loads(self.report_path.read_text(encoding='utf-8'))
        self.assertEqual(report['status'], 'FAIL')
        self.assertGreater(report['summary']['issue_count'], 0)
        self.assertEqual(report['checks']['marked_work_files']['status'], 'FAIL')
        chunk_check = report['checks'][
            'unfinished_chunked_uploads_and_chunk_directories'
        ]
        self.assertEqual(chunk_check['status'], 'FAIL')
        self.assertEqual(chunk_check['unfinished_uploads'], 1)
        self.assertEqual(chunk_check['chunk_directory_issues'], 1)
        self.assertEqual(report['checks']['uploaded_video_sha256']['status'], 'FAIL')

    def test_refuses_non_loadtest_database_without_override(self):
        with mock.patch.dict(connection.settings_dict, {'NAME': 'new_hire_gallery'}):
            with self.assertRaisesMessage(CommandError, '必须包含 loadtest'):
                call_command(
                    'verify_load_test',
                    output=self.report_path,
                    stdout=StringIO(),
                )
        self.assertFalse(self.report_path.exists())

    def test_explicit_read_only_clone_override_remains_read_only(self):
        self.create_valid_loadtest_data()
        before = list(
            Work.objects.order_by('id').values_list('id', 'updated_at')
        )

        self.call_command_in_database(
            'isolated_verification_clone',
            allow_read_only_clone=True,
            **self.minimum_options(),
        )

        after = list(
            Work.objects.order_by('id').values_list('id', 'updated_at')
        )
        self.assertEqual(after, before)
        report = json.loads(self.report_path.read_text(encoding='utf-8'))
        self.assertEqual(report['status'], 'PASS')
        self.assertFalse(report['database_safety']['name_contains_loadtest'])
        self.assertTrue(report['database_safety']['read_only_clone_override'])
    def test_empty_seed_and_zero_activity_cannot_pass(self):
        User.objects.create_user(username='loadtest_empty_user', password='irrelevant')

        with self.assertRaisesMessage(CommandError, '验收未通过'):
            self.call_command_in_database(
                'new_hire_gallery_loadtest',
                **self.minimum_options(),
            )

        report = json.loads(self.report_path.read_text(encoding='utf-8'))
        minimum_check = report['checks']['minimum_activity']
        self.assertEqual(report['status'], 'FAIL')
        self.assertEqual(minimum_check['status'], 'FAIL')
        self.assertEqual(minimum_check['metrics']['seed_targets']['actual'], 0)
        self.assertEqual(minimum_check['metrics']['likes']['actual'], 0)
        self.assertEqual(minimum_check['metrics']['votes']['actual'], 0)

    def test_video_sha_check_is_explicit_skip_when_minimum_is_zero(self):
        today = timezone.localdate()
        camp = TrainingCamp.objects.create(
            name='Read-only load test',
            slug='loadtest_read_only',
            start_date=today,
            end_date=today,
            is_active=True,
        )
        user = User.objects.create_user(
            username='loadtest_read_only_user',
            password='irrelevant',
        )
        Work.objects.create(
            camp=camp,
            author=user,
            title='[LOADTEST] read-only target',
            work_type=Work.WorkType.TRAINING,
            media_type=Work.MediaType.LINK,
            link='https://example.com/read-only',
            description='read-only seed',
            status=Work.Status.APPROVED,
        )

        self.call_command_in_database(
            'new_hire_gallery_loadtest',
            expected_users=1,
            expected_seed_targets=1,
            min_likes=0,
            min_votes=0,
            min_uploaded_image_works=0,
            min_uploaded_video_works=0,
        )

        report = json.loads(self.report_path.read_text(encoding='utf-8'))
        self.assertEqual(report['status'], 'PASS')
        self.assertEqual(report['checks']['uploaded_video_sha256']['status'], 'SKIP')

    def test_negative_minimum_is_rejected_before_report(self):
        with self.assertRaisesMessage(CommandError, '必须是非负整数'):
            self.call_command_in_database(
                'new_hire_gallery_loadtest',
                expected_users=-1,
            )
        self.assertFalse(self.report_path.exists())
