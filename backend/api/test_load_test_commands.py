import csv
import tempfile
from datetime import date, timedelta
from io import StringIO
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import TestCase, override_settings
from django.utils import timezone

from .management.commands.prepare_load_test import (
    DEFAULT_IMAGE_SIZE_MIB,
    DEFAULT_VIDEO_SIZE_MIB,
    MIB,
)
from .models import ChunkedUpload, Course, Profile, Tag, TrainingCamp, Work


LOADTEST_DATABASE_NAME = 'new_hire_gallery_loadtest'


@override_settings(
    PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],
)
class LoadTestManagementCommandTests(TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory(
            prefix='new_hire_gallery_loadtest_command_test_'
        )
        self.test_dir = Path(self.temporary_directory.name)
        self.settings_override = override_settings(
            MEDIA_ROOT=self.test_dir / 'media',
            WORK_UPLOAD_CHUNK_DIR=self.test_dir / 'chunks',
        )
        self.settings_override.enable()
        self.credentials_path = self.test_dir / 'credentials.csv'

    def tearDown(self):
        self.settings_override.disable()
        self.temporary_directory.cleanup()

    def call_in_loadtest_database(self, command_name, *args, **kwargs):
        if command_name == 'prepare_load_test':
            kwargs.setdefault('image_size_mib', 0.01)
            kwargs.setdefault('video_size_mib', 0.02)
        with mock.patch.dict(
            connection.settings_dict,
            {'NAME': LOADTEST_DATABASE_NAME},
        ):
            return call_command(command_name, *args, **kwargs)

    def test_commands_refuse_database_without_loadtest_in_name(self):
        with mock.patch.dict(connection.settings_dict, {'NAME': 'new_hire_gallery'}):
            with self.assertRaisesMessage(CommandError, '必须包含 loadtest'):
                call_command(
                    'prepare_load_test',
                    output=self.credentials_path,
                    stdout=StringIO(),
                )
            with self.assertRaisesMessage(CommandError, '必须包含 loadtest'):
                call_command('cleanup_load_test', stdout=StringIO())

        self.assertFalse(self.credentials_path.exists())
        self.assertFalse(User.objects.filter(username__startswith='loadtest_').exists())

    def test_prepare_creates_default_accounts_targets_media_and_private_csv(self):
        output = StringIO()
        self.call_in_loadtest_database(
            'prepare_load_test',
            output=self.credentials_path,
            stdout=output,
        )

        users = User.objects.filter(username__startswith='loadtest_').order_by('username')
        self.assertEqual(users.count(), 100)
        self.assertEqual(users.values('username').distinct().count(), 100)
        self.assertEqual(
            Profile.objects.filter(user__in=users, role=Profile.Role.STUDENT).count(),
            100,
        )

        camp = TrainingCamp.objects.get(slug='loadtest_camp')
        self.assertTrue(camp.is_active)
        self.assertLess(camp.submission_starts_at, camp.submission_ends_at)
        self.assertLess(camp.voting_starts_at, camp.voting_ends_at)
        targets = Work.objects.filter(
            camp=camp,
            title__startswith='[LOADTEST] AI loadtest target',
        )
        self.assertEqual(targets.count(), 200)
        self.assertEqual(
            targets.exclude(status=Work.Status.APPROVED).count(),
            0,
        )
        self.assertEqual(
            targets.exclude(title__icontains='AI').count(),
            0,
        )
        self.assertEqual(
            targets.exclude(description__icontains='loadtest').count(),
            0,
        )
        self.assertEqual(
            targets.filter(tags__name='loadtest_AI').distinct().count(),
            200,
        )
        self.assertGreaterEqual(
            targets.filter(media_type=Work.MediaType.IMAGE).count(),
            50,
        )
        self.assertGreaterEqual(
            targets.filter(media_type=Work.MediaType.VIDEO).count(),
            20,
        )
        self.assertEqual(Course.objects.filter(camp=camp).count(), 30)
        self.assertEqual(Tag.objects.filter(name__startswith='loadtest_').count(), 5)
        image_target = targets.filter(media_type=Work.MediaType.IMAGE).first()
        video_target = targets.filter(media_type=Work.MediaType.VIDEO).first()
        self.assertTrue(image_target.image)
        self.assertTrue(video_target.attachment)
        image_path = Path(image_target.image.path)
        video_path = Path(video_target.attachment.path)
        self.assertTrue(image_path.is_file())
        self.assertTrue(video_path.is_file())
        self.assertEqual(image_path.stat().st_size, round(0.01 * MIB))
        self.assertEqual(video_path.stat().st_size, round(0.02 * MIB))
        self.assertEqual(video_target.file_size, round(0.02 * MIB))
        with image_path.open('rb') as image_file:
            self.assertEqual(image_file.read(2), bytes((0xFF, 0xD8)))
        with video_path.open('rb') as video_file:
            video_file.seek(4)
            self.assertEqual(video_file.read(4), b'ftyp')

        with self.credentials_path.open(encoding='utf-8', newline='') as csv_file:
            rows = list(csv.DictReader(csv_file))
        self.assertEqual(len(rows), 100)
        self.assertEqual(len({row['username'] for row in rows}), 100)
        self.assertEqual(len({row['password'] for row in rows}), 100)

        first_row = rows[0]
        first_user = User.objects.get(username=first_row['username'])
        self.assertTrue(first_user.check_password(first_row['password']))
        for row in rows:
            self.assertNotIn(row['password'], output.getvalue())
        self.assertIn('Passwords are stored only', output.getvalue())

    def test_media_size_defaults_are_realistic(self):
        self.assertEqual(DEFAULT_IMAGE_SIZE_MIB, 2)
        self.assertEqual(DEFAULT_VIDEO_SIZE_MIB, 50)

    def test_prepare_accepts_minimum_counts(self):
        self.call_in_loadtest_database(
            'prepare_load_test',
            output=self.credentials_path,
            users=1,
            targets=20,
            stdout=StringIO(),
        )

        self.assertEqual(User.objects.filter(username__startswith='loadtest_').count(), 1)
        self.assertEqual(Work.objects.filter(title__startswith='[LOADTEST]').count(), 20)

    def test_prepare_accepts_maximum_counts_for_large_runner(self):
        self.call_in_loadtest_database(
            'prepare_load_test',
            output=self.credentials_path,
            users=1000,
            targets=1000,
            stdout=StringIO(),
        )

        self.assertEqual(User.objects.filter(username__startswith='loadtest_').count(), 1000)
        self.assertEqual(Work.objects.filter(title__startswith='[LOADTEST]').count(), 1000)
        with self.credentials_path.open(encoding='utf-8', newline='') as csv_file:
            self.assertEqual(sum(1 for _ in csv.DictReader(csv_file)), 1000)

    def test_prepare_rejects_counts_outside_safe_bounds(self):
        invalid_options = [
            {'users': 0},
            {'users': 1001},
            {'users': 'not-a-number'},
            {'targets': 19},
            {'targets': 1001},
            {'targets': 'not-a-number'},
            {'image_size_mib': 0},
            {'image_size_mib': 101},
            {'image_size_mib': 'not-a-number'},
            {'image_size_mib': float('nan')},
            {'video_size_mib': 0},
            {'video_size_mib': 1025},
            {'video_size_mib': float('inf')},
        ]
        for options in invalid_options:
            with self.subTest(options=options):
                with self.assertRaisesMessage(CommandError, 'must be'):
                    self.call_in_loadtest_database(
                        'prepare_load_test',
                        output=self.credentials_path,
                        stdout=StringIO(),
                        **options,
                    )

        self.assertFalse(self.credentials_path.exists())
        self.assertFalse(User.objects.filter(username__startswith='loadtest_').exists())

    def test_prepare_refuses_to_overwrite_credentials_file(self):
        self.credentials_path.write_text('do-not-overwrite', encoding='utf-8')

        with self.assertRaisesMessage(CommandError, '拒绝覆盖'):
            self.call_in_loadtest_database(
                'prepare_load_test',
                output=self.credentials_path,
                stdout=StringIO(),
            )

        self.assertEqual(
            self.credentials_path.read_text(encoding='utf-8'),
            'do-not-overwrite',
        )
        self.assertFalse(User.objects.filter(username__startswith='loadtest_').exists())

    def test_prepare_rolls_back_database_if_credentials_cannot_be_published(self):
        with mock.patch(
            'api.management.commands.prepare_load_test.os.replace',
            side_effect=OSError('simulated disk failure'),
        ):
            with self.assertRaises(OSError):
                self.call_in_loadtest_database(
                    'prepare_load_test',
                    output=self.credentials_path,
                    stdout=StringIO(),
                )

        self.assertFalse(self.credentials_path.exists())
        self.assertFalse(User.objects.filter(username__startswith='loadtest_').exists())
        self.assertFalse(TrainingCamp.objects.filter(slug__startswith='loadtest_').exists())
        self.assertEqual(list(self.test_dir.glob('*.tmp')), [])
        self.assertEqual(list(Path(settings.MEDIA_ROOT).rglob('*.*')), [])

    def test_cleanup_deletes_only_fixed_prefix_data(self):
        ordinary_user = User.objects.create_user(
            username='ordinary_student',
            password='OrdinaryPass123!',
        )
        ordinary_camp = TrainingCamp.objects.create(
            name='普通培训期',
            slug='ordinary-camp',
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 2),
            is_active=False,
        )
        ordinary_tag = Tag.objects.create(name='ordinary-tag')
        ordinary_work = Work.objects.create(
            camp=ordinary_camp,
            author=ordinary_user,
            title='普通作品',
            work_type=Work.WorkType.TRAINING,
            media_type=Work.MediaType.LINK,
            link='https://example.com/ordinary',
            description='不能被压测清理命令删除。',
            status=Work.Status.APPROVED,
        )

        self.call_in_loadtest_database(
            'prepare_load_test',
            output=self.credentials_path,
            stdout=StringIO(),
        )
        loadtest_camp = TrainingCamp.objects.get(slug='loadtest_camp')
        image_target = Work.objects.filter(
            camp=loadtest_camp,
            media_type=Work.MediaType.IMAGE,
        ).first()
        video_target = Work.objects.filter(
            camp=loadtest_camp,
            media_type=Work.MediaType.VIDEO,
        ).first()
        image_path = Path(image_target.image.path)
        video_path = Path(video_target.attachment.path)
        loadtest_user = User.objects.filter(username__startswith='loadtest_').first()
        interrupted_upload = ChunkedUpload.objects.create(
            camp=loadtest_camp,
            owner=loadtest_user,
            file_name='interrupted.mp4',
            content_type='video/mp4',
            media_type=Work.MediaType.VIDEO,
            total_size=1024,
            total_chunks=2,
            expires_at=timezone.now() + timedelta(hours=1),
        )
        chunk_dir = (
            Path(settings.WORK_UPLOAD_CHUNK_DIR)
            / str(interrupted_upload.upload_id)
        )
        chunk_dir.mkdir(parents=True, exist_ok=True)
        (chunk_dir / '00000000.part').write_bytes(b'partial upload')

        self.call_in_loadtest_database('cleanup_load_test', stdout=StringIO())

        self.assertFalse(User.objects.filter(username__startswith='loadtest_').exists())
        self.assertFalse(TrainingCamp.objects.filter(slug__startswith='loadtest_').exists())
        self.assertFalse(Work.objects.filter(title__startswith='[LOADTEST]').exists())
        self.assertFalse(Course.objects.filter(camp__slug__startswith='loadtest_').exists())
        self.assertFalse(Tag.objects.filter(name__startswith='loadtest_').exists())
        self.assertFalse(image_path.exists())
        self.assertFalse(video_path.exists())
        self.assertFalse(chunk_dir.exists())
        self.assertTrue(User.objects.filter(pk=ordinary_user.pk).exists())
        self.assertTrue(TrainingCamp.objects.filter(pk=ordinary_camp.pk).exists())
        self.assertTrue(Work.objects.filter(pk=ordinary_work.pk).exists())
        self.assertTrue(Tag.objects.filter(pk=ordinary_tag.pk).exists())
