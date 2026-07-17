import csv
import math
import os
import secrets
import struct
import tempfile
from datetime import time, timedelta
from io import BytesIO
from pathlib import Path

from django.contrib.auth.models import User
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone
from PIL import Image

from api.models import (
    Course,
    Profile,
    Tag,
    TrainingCamp,
    Work,
    normalize_tag_name,
)


LOADTEST_PREFIX = 'loadtest_'
LOADTEST_CAMP_SLUG = f'{LOADTEST_PREFIX}camp'
LOADTEST_CAMP_NAME = '[LOADTEST] 并发测试培训营'
LOADTEST_WORK_TITLE = '[LOADTEST] AI loadtest target'
DEFAULT_LOADTEST_USER_COUNT = 100
MAX_LOADTEST_USER_COUNT = 1000
MIN_LOADTEST_TARGET_COUNT = 20
DEFAULT_LOADTEST_TARGET_COUNT = 200
MAX_LOADTEST_TARGET_COUNT = 1000
MIB = 1024 * 1024
DEFAULT_IMAGE_SIZE_MIB = 2
DEFAULT_VIDEO_SIZE_MIB = 50
MIN_MEDIA_SIZE_MIB = 0.001
MAX_IMAGE_SIZE_MIB = 100
MAX_VIDEO_SIZE_MIB = 1024
STREAM_CHUNK_SIZE = MIB
LOADTEST_COURSE_COUNT = 30
LOADTEST_TAG_PREFIX = 'loadtest_'
LOADTEST_TAG_NAMES = (
    'loadtest_AI',
    'loadtest_AI_media',
    'loadtest_AI_image',
    'loadtest_AI_video',
    'loadtest_AI_link',
)
COURSE_TIME_SLOTS = (
    (time(8, 30), time(9, 15)),
    (time(9, 30), time(10, 15)),
    (time(10, 30), time(11, 15)),
    (time(14, 0), time(14, 45)),
    (time(15, 0), time(15, 45)),
)


def _write_zero_padding(file_object, byte_count):
    zero_chunk = bytes(STREAM_CHUNK_SIZE)
    remaining = byte_count
    while remaining:
        chunk_size = min(remaining, len(zero_chunk))
        file_object.write(zero_chunk[:chunk_size])
        remaining -= chunk_size


def write_loadtest_jpeg(path, total_size):
    buffer = BytesIO()
    Image.new('RGB', (32, 32), color=(255, 48, 72)).save(
        buffer,
        format='JPEG',
        quality=80,
    )
    jpeg_bytes = buffer.getvalue()
    if total_size < len(jpeg_bytes):
        raise CommandError(
            f'Image fixture size must be at least {len(jpeg_bytes)} bytes.'
        )
    with Path(path).open('wb') as fixture:
        fixture.write(jpeg_bytes)
        _write_zero_padding(fixture, total_size - len(jpeg_bytes))


def write_loadtest_mp4(path, total_size):
    ftyp_box = struct.pack(
        '>I4s4sI4s4s',
        24,
        b'ftyp',
        b'isom',
        0,
        b'isom',
        b'mp42',
    )
    minimum_size = len(ftyp_box) + 8
    if total_size < minimum_size:
        raise CommandError(f'Video fixture size must be at least {minimum_size} bytes.')
    payload_size = total_size - minimum_size
    with Path(path).open('wb') as fixture:
        fixture.write(ftyp_box)
        fixture.write(struct.pack('>I4s', 8 + payload_size, b'mdat'))
        _write_zero_padding(fixture, payload_size)


def require_loadtest_database():
    """Refuse to mutate any database whose configured name is not explicit."""
    database_name = str(connection.settings_dict.get('NAME') or '')
    if 'loadtest' not in database_name.casefold():
        raise CommandError(
            '安全检查失败：数据库名称必须包含 loadtest；'
            '请连接独立压测数据库后再执行。'
        )


class Command(BaseCommand):
    help = 'Prepare load-test accounts and approved target works in a dedicated loadtest database.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--output',
            required=True,
            help='保存压测账号凭据的 CSV 路径；为避免覆盖，目标文件必须不存在。',
        )
        parser.add_argument(
            '--users',
            type=int,
            default=DEFAULT_LOADTEST_USER_COUNT,
            help=f'Account count (1-{MAX_LOADTEST_USER_COUNT}; default {DEFAULT_LOADTEST_USER_COUNT}).',
        )
        parser.add_argument(
            '--targets',
            type=int,
            default=DEFAULT_LOADTEST_TARGET_COUNT,
            help=(
                f'Approved target-work count ({MIN_LOADTEST_TARGET_COUNT}-'
                f'{MAX_LOADTEST_TARGET_COUNT}; default {DEFAULT_LOADTEST_TARGET_COUNT}).'
            ),
        )
        parser.add_argument(
            '--image-size-mib',
            type=float,
            default=DEFAULT_IMAGE_SIZE_MIB,
            help=(
                f'Seed image size in MiB ({MIN_MEDIA_SIZE_MIB}-{MAX_IMAGE_SIZE_MIB}; '
                f'default {DEFAULT_IMAGE_SIZE_MIB}).'
            ),
        )
        parser.add_argument(
            '--video-size-mib',
            type=float,
            default=DEFAULT_VIDEO_SIZE_MIB,
            help=(
                f'Seed video size in MiB ({MIN_MEDIA_SIZE_MIB}-{MAX_VIDEO_SIZE_MIB}; '
                f'default {DEFAULT_VIDEO_SIZE_MIB}).'
            ),
        )

    def handle(self, *args, **options):
        require_loadtest_database()
        user_count = self._validate_count(
            options['users'],
            option_name='--users',
            maximum=MAX_LOADTEST_USER_COUNT,
        )
        target_count = self._validate_count(
            options['targets'],
            option_name='--targets',
            minimum=MIN_LOADTEST_TARGET_COUNT,
            maximum=MAX_LOADTEST_TARGET_COUNT,
        )
        image_size = self._validate_media_size(
            options['image_size_mib'],
            option_name='--image-size-mib',
            maximum=MAX_IMAGE_SIZE_MIB,
        )
        video_size = self._validate_media_size(
            options['video_size_mib'],
            option_name='--video-size-mib',
            maximum=MAX_VIDEO_SIZE_MIB,
        )

        output_path = Path(options['output']).expanduser().resolve()
        if output_path.exists():
            raise CommandError(f'凭据文件已存在，拒绝覆盖：{output_path}')

        if User.objects.filter(username__startswith=LOADTEST_PREFIX).exists():
            raise CommandError('检测到既有压测账号，请先执行 cleanup_load_test。')
        if TrainingCamp.objects.filter(slug__startswith=LOADTEST_PREFIX).exists():
            raise CommandError('检测到既有压测培训期，请先执行 cleanup_load_test。')
        if Work.objects.filter(title__startswith='[LOADTEST]').exists():
            raise CommandError('检测到既有压测作品，请先执行 cleanup_load_test。')
        if Tag.objects.filter(
            normalized_name__startswith=normalize_tag_name(LOADTEST_TAG_PREFIX)
        ).exists():
            raise CommandError('Existing load-test tags detected; run cleanup_load_test first.')

        output_path.parent.mkdir(parents=True, exist_ok=True)
        credentials = [
            (
                f'{LOADTEST_PREFIX}user_{index:03d}',
                secrets.token_urlsafe(24),
            )
            for index in range(1, user_count + 1)
        ]

        temporary_path = None
        created_media = []
        try:
            temporary_path = self._write_credentials(output_path, credentials)
            try:
                with transaction.atomic():
                    camp, target_works = self._create_database_records(
                        credentials,
                        target_count=target_count,
                        image_size=image_size,
                        video_size=video_size,
                        created_media=created_media,
                    )
                    os.replace(temporary_path, output_path)
                    temporary_path = None
            except Exception:
                for storage, stored_name in created_media:
                    storage.delete(stored_name)
                output_path.unlink(missing_ok=True)
                raise
            try:
                os.chmod(output_path, 0o600)
            except OSError:
                # Some Windows filesystems do not implement POSIX permissions.
                pass
        finally:
            if temporary_path:
                Path(temporary_path).unlink(missing_ok=True)

        self.stdout.write(self.style.SUCCESS(
            f'Load-test data ready: {user_count} accounts and '
            f'{len(target_works)} approved target works.'
        ))
        self.stdout.write(
            f'{LOADTEST_COURSE_COUNT} courses and {len(LOADTEST_TAG_NAMES)} tags created.'
        )
        self.stdout.write(
            f'Seed media sizes: image={image_size / MIB:.3f} MiB, '
            f'video={video_size / MIB:.3f} MiB.'
        )
        self.stdout.write(f'Training camp ID: {camp.pk}')
        self.stdout.write(
            f'Target work ID range: {target_works[0].pk}-{target_works[-1].pk}'
        )
        self.stdout.write(f'Credentials CSV: {output_path}')
        self.stdout.write('Passwords are stored only in the credentials CSV and are never printed.')

    @staticmethod
    def _validate_count(value, *, option_name, maximum, minimum=1):
        try:
            count = int(value)
        except (TypeError, ValueError) as exc:
            raise CommandError(f'{option_name} must be an integer.') from exc
        if not minimum <= count <= maximum:
            raise CommandError(
                f'{option_name} must be between {minimum} and {maximum}.'
            )
        return count

    @staticmethod
    def _validate_media_size(value, *, option_name, maximum):
        try:
            size_mib = float(value)
        except (TypeError, ValueError) as exc:
            raise CommandError(f'{option_name} must be a number.') from exc
        if not math.isfinite(size_mib) or not MIN_MEDIA_SIZE_MIB <= size_mib <= maximum:
            raise CommandError(
                f'{option_name} must be between {MIN_MEDIA_SIZE_MIB} and {maximum} MiB.'
            )
        return round(size_mib * MIB)


    @staticmethod
    def _write_credentials(output_path, credentials):
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f'.{output_path.name}.',
            suffix='.tmp',
            dir=output_path.parent,
            text=True,
        )
        try:
            with os.fdopen(descriptor, 'w', encoding='utf-8', newline='') as csv_file:
                writer = csv.DictWriter(csv_file, fieldnames=['username', 'password'])
                writer.writeheader()
                for username, password in credentials:
                    writer.writerow({'username': username, 'password': password})
            try:
                os.chmod(temporary_name, 0o600)
            except OSError:
                pass
            return temporary_name
        except Exception:
            Path(temporary_name).unlink(missing_ok=True)
            raise

    @staticmethod
    def _create_database_records(
        credentials, *, target_count, image_size, video_size, created_media
    ):
        now = timezone.now()
        today = timezone.localdate()

        with transaction.atomic():
            camp = TrainingCamp.objects.create(
                name=LOADTEST_CAMP_NAME,
                slug=LOADTEST_CAMP_SLUG,
                start_date=today - timedelta(days=1),
                end_date=today + timedelta(days=30),
                submission_starts_at=now - timedelta(days=1),
                submission_ends_at=now + timedelta(days=30),
                voting_starts_at=now - timedelta(days=1),
                voting_ends_at=now + timedelta(days=30),
                vote_limit=5,
                is_active=True,
            )

            users = []
            for index, (username, password) in enumerate(credentials, start=1):
                user = User.objects.create_user(username=username, password=password)
                profile = user.profile
                profile.name = f'压测学员{index:03d}'
                profile.role = Profile.Role.STUDENT
                profile.training_group = str(((index - 1) % 6) + 1)
                profile.save(update_fields=['name', 'role', 'training_group', 'updated_at'])
                users.append(user)

            tags = {
                name: Tag.objects.create(name=name)
                for name in LOADTEST_TAG_NAMES
            }
            for index in range(1, LOADTEST_COURSE_COUNT + 1):
                starts_at, ends_at = COURSE_TIME_SLOTS[(index - 1) % len(COURSE_TIME_SLOTS)]
                Course.objects.create(
                    camp=camp,
                    title=f'[LOADTEST] AI loadtest course {index:03d}',
                    topic='AI loadtest concurrency course',
                    teacher=f'Loadtest teacher {((index - 1) % 5) + 1}',
                    room=f'Loadtest room {((index - 1) % 3) + 1}',
                    content='AI loadtest course content for course-list and search traffic.',
                    date=today + timedelta(days=(index - 1) // len(COURSE_TIME_SLOTS)),
                    start_time=starts_at,
                    end_time=ends_at,
                    status=Course.Status.UPCOMING,
                    sort_order=index,
                )

            with tempfile.TemporaryDirectory(
                prefix='new_hire_gallery_loadtest_media_'
            ) as template_directory:
                template_directory = Path(template_directory)
                image_template = template_directory / 'seed-image.jpg'
                video_template = template_directory / 'seed-video.mp4'
                write_loadtest_jpeg(image_template, image_size)
                write_loadtest_mp4(video_template, video_size)

                target_works = []
                for index in range(1, target_count + 1):
                    is_video = index % 10 == 0
                    is_image = not is_video and index % 3 == 0
                    work = Work(
                        camp=camp,
                        author=users[(index - 1) % len(users)],
                        title=f'{LOADTEST_WORK_TITLE} {index:04d}',
                        work_type=(
                            Work.WorkType.AI
                            if index % 2
                            else Work.WorkType.TRAINING
                        ),
                        media_type=Work.MediaType.LINK,
                        link=f'https://example.com/loadtest-ai-target-{index:04d}',
                        description=(
                            f'AI loadtest approved work {index:04d} for browse, '
                            'search, tags, leaderboard, likes, and votes.'
                        ),
                        status=Work.Status.APPROVED,
                    )
                    media_tag = tags['loadtest_AI_link']
                    if is_image:
                        work.media_type = Work.MediaType.IMAGE
                        work.link = ''
                        with image_template.open('rb') as image_file:
                            work.image.save(
                                f'{LOADTEST_PREFIX}target_{index:04d}.jpg',
                                File(image_file),
                                save=False,
                            )
                        created_media.append((work.image.storage, work.image.name))
                        media_tag = tags['loadtest_AI_image']
                    elif is_video:
                        work.media_type = Work.MediaType.VIDEO
                        work.link = ''
                        with video_template.open('rb') as video_file:
                            work.attachment.save(
                                f'{LOADTEST_PREFIX}target_{index:04d}.mp4',
                                File(video_file),
                                save=False,
                            )
                        created_media.append((work.attachment.storage, work.attachment.name))
                        work.original_filename = f'{LOADTEST_PREFIX}target_{index:04d}.mp4'
                        work.content_type = 'video/mp4'
                        work.file_size = video_size
                        media_tag = tags['loadtest_AI_video']
                    work.save()
                    work.tags.set([
                        tags['loadtest_AI'],
                        tags['loadtest_AI_media'],
                        media_tag,
                    ])
                    target_works.append(work)

        return camp, target_works
