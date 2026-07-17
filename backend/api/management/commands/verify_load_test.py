import hashlib
import json
from datetime import datetime, timezone as datetime_timezone
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.models import Count, Q

from api.models import ChunkedUpload, Like, Vote, Work


LOADTEST_USER_PREFIX = 'loadtest_'
LOADTEST_UPLOAD_TITLE_PREFIX = 'loadtest-'
LOADTEST_SEED_TITLE_PREFIX = '[LOADTEST]'
MAX_EXAMPLES = 20


class Command(BaseCommand):
    help = '只读验收压测后的关系数据、媒体文件、视频摘要和分片清理状态。'

    def add_arguments(self, parser):
        parser.add_argument(
            '--output',
            required=True,
            help='写入脱敏 JSON 验收报告的路径。',
        )
        parser.add_argument(
            '--allow-read-only-clone',
            action='store_true',
            help=(
                '仅当当前库是隔离的只读克隆库时允许库名不含 loadtest；'
                '本命令仍不会修改数据库。'
            ),
        )
        parser.add_argument('--expected-users', type=int, default=100)
        parser.add_argument('--expected-seed-targets', type=int, default=200)
        parser.add_argument('--min-likes', type=int, default=1)
        parser.add_argument('--min-votes', type=int, default=1)
        parser.add_argument('--min-uploaded-image-works', type=int, default=1)
        parser.add_argument('--min-uploaded-video-works', type=int, default=1)

    def handle(self, *args, **options):
        output_path = Path(options['output']).expanduser().resolve()
        database_name = str(connection.settings_dict.get('NAME') or '')
        database_is_loadtest = 'loadtest' in database_name.casefold()
        read_only_override = bool(options['allow_read_only_clone'])
        if not database_is_loadtest and not read_only_override:
            raise CommandError(
                '安全检查失败：数据库名称必须包含 loadtest；'
                '若已连接隔离的只读克隆库，可显式加 '
                '--allow-read-only-clone。'
            )

        minimums = {
            'loadtest_users': self._nonnegative(options['expected_users'], '--expected-users'),
            'seed_targets': self._nonnegative(
                options['expected_seed_targets'], '--expected-seed-targets'
            ),
            'likes': self._nonnegative(options['min_likes'], '--min-likes'),
            'votes': self._nonnegative(options['min_votes'], '--min-votes'),
            'uploaded_image_works': self._nonnegative(
                options['min_uploaded_image_works'], '--min-uploaded-image-works'
            ),
            'uploaded_video_works': self._nonnegative(
                options['min_uploaded_video_works'], '--min-uploaded-video-works'
            ),
        }
        report = self._build_report(
            database_is_loadtest=database_is_loadtest,
            read_only_override=read_only_override,
            minimums=minimums,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + '\n',
            encoding='utf-8',
        )

        summary = report['summary']
        self.stdout.write(
            '压测数据验收：'
            f"{report['status']}；压测账号 {summary['loadtest_users']} 个，"
            f"作品 {summary['scoped_works']} 个，问题 {summary['issue_count']} 个。"
        )
        self.stdout.write(f'脱敏 JSON 报告已写入：{output_path}')
        if report['skipped_checks']:
            self.stdout.write(
                self.style.WARNING(
                    f"有 {len(report['skipped_checks'])} 项检查未完成，不按通过处理。"
                )
            )

        if report['status'] != 'PASS':
            raise CommandError(
                '压测数据验收未通过，请根据 JSON 报告排查。'
            )
        self.stdout.write(self.style.SUCCESS('压测数据一致性验收通过。'))

    @staticmethod
    def _nonnegative(value, option_name):
        if value is None or value < 0:
            raise CommandError(f'{option_name} 必须是非负整数。')
        return value

    def _build_report(self, *, database_is_loadtest, read_only_override, minimums):
        loadtest_users = User.objects.filter(
            username__startswith=LOADTEST_USER_PREFIX
        )
        loadtest_user_ids = list(loadtest_users.values_list('id', flat=True))

        duplicate_likes = self._duplicate_pairs(Like, loadtest_user_ids)
        duplicate_votes = self._duplicate_pairs(Vote, loadtest_user_ids)

        interacted_work_ids = set(
            Like.objects.filter(user_id__in=loadtest_user_ids).values_list(
                'work_id', flat=True
            )
        )
        interacted_work_ids.update(
            Vote.objects.filter(user_id__in=loadtest_user_ids).values_list(
                'work_id', flat=True
            )
        )
        marked_works = Work.objects.filter(
            Q(author_id__in=loadtest_user_ids)
            | Q(title__istartswith=LOADTEST_UPLOAD_TITLE_PREFIX)
            | Q(title__startswith=LOADTEST_SEED_TITLE_PREFIX)
        )
        scoped_work_ids = set(marked_works.values_list('id', flat=True))
        scoped_work_ids.update(interacted_work_ids)

        actuals = {
            'loadtest_users': len(loadtest_user_ids),
            'seed_targets': Work.objects.filter(
                title__startswith=LOADTEST_SEED_TITLE_PREFIX
            ).count(),
            'likes': Like.objects.filter(user_id__in=loadtest_user_ids).count(),
            'votes': Vote.objects.filter(user_id__in=loadtest_user_ids).count(),
            'uploaded_image_works': Work.objects.filter(
                title__istartswith=LOADTEST_UPLOAD_TITLE_PREFIX,
                media_type=Work.MediaType.IMAGE,
            ).count(),
            'uploaded_video_works': Work.objects.filter(
                title__istartswith=LOADTEST_UPLOAD_TITLE_PREFIX,
                media_type=Work.MediaType.VIDEO,
            ).count(),
        }
        minimum_issues = [
            {
                'metric': metric,
                'actual': actuals[metric],
                'expected_minimum': expected,
                'reason': 'minimum_activity_not_reached',
            }
            for metric, expected in minimums.items()
            if actuals[metric] < expected
        ]
        minimum_metrics = {
            metric: {
                'actual': actuals[metric],
                'expected_minimum': expected,
            }
            for metric, expected in minimums.items()
        }

        count_mismatches = self._count_mismatches(scoped_work_ids)
        file_result, video_result = self._verify_files_and_video_hashes(
            minimum_uploaded_video_works=minimums['uploaded_video_works']
        )
        chunk_result = self._verify_chunk_state(loadtest_user_ids)

        checks = {
            'minimum_activity': self._check_result(
                minimum_issues,
                extra={'metrics': minimum_metrics},
            ),
            'duplicate_like_pairs': self._check_result(duplicate_likes),
            'duplicate_vote_pairs': self._check_result(duplicate_votes),
            'display_relation_counts': self._check_result(
                count_mismatches,
                extra={'display_count_source': 'runtime_distinct_relation_annotation'},
            ),
            'marked_work_files': file_result,
            'uploaded_video_sha256': video_result,
            'unfinished_chunked_uploads_and_chunk_directories': chunk_result,
        }
        skipped_checks = []
        issue_count = sum(check['issue_count'] for check in checks.values())
        status = 'PASS' if issue_count == 0 and not skipped_checks else 'FAIL'

        return {
            'schema_version': 1,
            'generated_at': datetime.now(datetime_timezone.utc).isoformat(),
            'status': status,
            'database_safety': {
                'name_contains_loadtest': database_is_loadtest,
                'read_only_clone_override': read_only_override,
                'database_writes_performed': False,
            },
            'scope': {
                'user_prefix': LOADTEST_USER_PREFIX,
                'upload_title_prefix': LOADTEST_UPLOAD_TITLE_PREFIX,
            },
            'summary': {
                'loadtest_users': len(loadtest_user_ids),
                'scoped_works': len(scoped_work_ids),
                'issue_count': issue_count,
            },
            'checks': checks,
            'skipped_checks': skipped_checks,
        }

    @staticmethod
    def _duplicate_pairs(model, loadtest_user_ids):
        return list(
            model.objects.filter(user_id__in=loadtest_user_ids)
            .values('user_id', 'work_id')
            .annotate(relation_rows=Count('id'))
            .filter(relation_rows__gt=1)
            .order_by('user_id', 'work_id')[:MAX_EXAMPLES]
        )

    @staticmethod
    def _count_mismatches(scoped_work_ids):
        if not scoped_work_ids:
            return []
        displayed = Work.objects.filter(pk__in=scoped_work_ids).annotate(
            displayed_like_count=Count('likes', distinct=True),
            displayed_vote_count=Count('votes', distinct=True),
        )
        true_likes = {
            row['work_id']: row['count']
            for row in Like.objects.filter(work_id__in=scoped_work_ids)
            .values('work_id')
            .annotate(count=Count('id'))
        }
        true_votes = {
            row['work_id']: row['count']
            for row in Vote.objects.filter(work_id__in=scoped_work_ids)
            .values('work_id')
            .annotate(count=Count('id'))
        }
        mismatches = []
        for work in displayed.iterator():
            actual_likes = true_likes.get(work.pk, 0)
            actual_votes = true_votes.get(work.pk, 0)
            if (
                work.displayed_like_count != actual_likes
                or work.displayed_vote_count != actual_votes
            ):
                mismatches.append({
                    'work_id': work.pk,
                    'displayed_like_count': work.displayed_like_count,
                    'relation_like_rows': actual_likes,
                    'displayed_vote_count': work.displayed_vote_count,
                    'relation_vote_rows': actual_votes,
                })
                if len(mismatches) >= MAX_EXAMPLES:
                    break
        return mismatches

    def _verify_files_and_video_hashes(self, *, minimum_uploaded_video_works):
        marked_media = Work.objects.filter(
            Q(title__istartswith=LOADTEST_UPLOAD_TITLE_PREFIX)
            | Q(title__startswith=LOADTEST_SEED_TITLE_PREFIX),
            media_type__in=[Work.MediaType.IMAGE, Work.MediaType.VIDEO],
        ).prefetch_related('gallery_images')
        file_issues = []
        video_hash_issues = []
        checked_files = 0
        checked_video_hashes = 0
        uploaded_video_candidates = 0

        for work in marked_media.iterator(chunk_size=100):
            if work.media_type == Work.MediaType.IMAGE:
                fields = []
                if work.image:
                    fields.append(work.image)
                fields.extend(image.image for image in work.gallery_images.all())
                if not fields:
                    file_issues.append({
                        'work_id': work.pk,
                        'reason': 'image_work_has_no_local_file',
                    })
                for field_file in fields:
                    checked_files += 1
                    problem = self._stored_file_problem(field_file)
                    if problem:
                        file_issues.append({
                            'work_id': work.pk,
                            'media_type': Work.MediaType.IMAGE,
                            'reason': problem,
                        })
            elif work.media_type == Work.MediaType.VIDEO:
                is_uploaded_video = work.title.casefold().startswith(
                    LOADTEST_UPLOAD_TITLE_PREFIX.casefold()
                )
                if is_uploaded_video:
                    uploaded_video_candidates += 1
                checked_files += 1
                problem = self._stored_file_problem(work.attachment)
                if problem:
                    file_issues.append({
                        'work_id': work.pk,
                        'media_type': Work.MediaType.VIDEO,
                        'reason': problem,
                    })
                    if is_uploaded_video:
                        video_hash_issues.append({
                            'work_id': work.pk,
                            'reason': 'final_video_unreadable_for_sha256',
                        })
                    continue

                # Seed videos intentionally have no ChunkedUpload. Uploaded
                # load-test videos must retain a consumed upload record so the
                # final file digest can be independently verified.
                if not is_uploaded_video:
                    continue
                uploads = list(
                    ChunkedUpload.objects.filter(
                        owner_id=work.author_id,
                        camp_id=work.camp_id,
                        media_type=Work.MediaType.VIDEO,
                        status=ChunkedUpload.Status.CONSUMED,
                        file=work.attachment.name,
                    ).order_by('-created_at')[:2]
                )
                if len(uploads) != 1:
                    video_hash_issues.append({
                        'work_id': work.pk,
                        'reason': 'consumed_upload_sha_source_not_unique',
                        'matching_uploads': len(uploads),
                    })
                    continue
                upload = uploads[0]
                if not upload.sha256:
                    video_hash_issues.append({
                        'work_id': work.pk,
                        'upload_id': str(upload.upload_id),
                        'reason': 'consumed_upload_sha256_missing',
                    })
                    continue
                checked_video_hashes += 1
                actual_sha256 = self._sha256(work.attachment)
                if actual_sha256 != upload.sha256:
                    video_hash_issues.append({
                        'work_id': work.pk,
                        'upload_id': str(upload.upload_id),
                        'reason': 'final_video_sha256_mismatch',
                    })
                elif upload.expected_sha256 and actual_sha256 != upload.expected_sha256:
                    video_hash_issues.append({
                        'work_id': work.pk,
                        'upload_id': str(upload.upload_id),
                        'reason': 'final_video_expected_sha256_mismatch',
                    })

        video_result = self._check_result(
            video_hash_issues,
            extra={
                'uploaded_video_candidates': uploaded_video_candidates,
                'checked_video_hashes': checked_video_hashes,
            },
        )
        if uploaded_video_candidates == 0 and minimum_uploaded_video_works == 0:
            video_result.update({
                'status': 'SKIP',
                'reason': 'no_uploaded_video_and_minimum_is_zero',
            })

        return (
            self._check_result(
                file_issues,
                extra={'checked_files': checked_files},
            ),
            video_result,
        )

    @staticmethod
    def _stored_file_problem(field_file):
        if not field_file or not field_file.name:
            return 'file_reference_missing'
        try:
            if not field_file.storage.exists(field_file.name):
                return 'stored_file_missing'
            if field_file.storage.size(field_file.name) <= 0:
                return 'stored_file_empty'
        except (OSError, ValueError):
            return 'stored_file_unreadable'
        return ''

    @staticmethod
    def _sha256(field_file):
        digest = hashlib.sha256()
        with field_file.storage.open(field_file.name, 'rb') as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _verify_chunk_state(loadtest_user_ids):
        test_uploads = ChunkedUpload.objects.filter(owner_id__in=loadtest_user_ids)
        unfinished = list(
            test_uploads.exclude(status=ChunkedUpload.Status.CONSUMED)
            .values('upload_id', 'status', 'total_chunks')
            .order_by('created_at')[:MAX_EXAMPLES]
        )
        known_uploads = {
            str(upload_id): status
            for upload_id, status in test_uploads.values_list('upload_id', 'status')
        }
        directory_issues = []
        chunk_root = Path(settings.WORK_UPLOAD_CHUNK_DIR)
        if chunk_root.exists():
            try:
                entries = sorted(chunk_root.iterdir(), key=lambda entry: entry.name)
            except OSError:
                entries = []
                directory_issues.append({'reason': 'chunk_root_unreadable'})
            for entry in entries:
                upload_status = known_uploads.get(entry.name)
                if entry.is_dir():
                    if upload_status:
                        reason = 'chunk_directory_left_for_known_upload'
                    else:
                        reason = 'orphan_chunk_directory'
                    directory_issues.append({
                        'upload_id': entry.name,
                        'upload_status': upload_status or 'unknown',
                        'reason': reason,
                    })
                else:
                    directory_issues.append({
                        'entry_name': entry.name,
                        'reason': 'unexpected_non_directory_entry',
                    })
                if len(directory_issues) >= MAX_EXAMPLES:
                    break

        issues = [
            {
                'upload_id': str(item['upload_id']),
                'status': item['status'],
                'total_chunks': item['total_chunks'],
                'reason': 'upload_not_consumed',
            }
            for item in unfinished
        ]
        issues.extend(directory_issues[: max(0, MAX_EXAMPLES - len(issues))])
        return Command._check_result(
            issues,
            extra={
                'unfinished_uploads': len(unfinished),
                'chunk_directory_issues': len(directory_issues),
            },
        )

    @staticmethod
    def _check_result(issues, *, extra=None):
        result = {
            'status': 'PASS' if not issues else 'FAIL',
            'issue_count': len(issues),
            'examples': issues[:MAX_EXAMPLES],
        }
        if extra:
            result.update(extra)
        return result
