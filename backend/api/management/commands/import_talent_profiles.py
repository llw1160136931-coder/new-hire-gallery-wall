import hashlib
import html
import re
import unicodedata
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from api.models import (
    Profile,
    TalentProfileReport,
    TrainingCamp,
    TrainingCampMembership,
)


MAX_REPORT_COUNT = 500
MAX_REPORT_SIZE = 2 * 1024 * 1024
MAX_ARCHIVE_UNCOMPRESSED_SIZE = 100 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200
REPORT_SUFFIX = '-新员工人才画像报告.html'
ALLOWED_CHART_JS_URL = 'https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js'
REPORT_FILENAME_PATTERN = re.compile(
    rf'^(?P<sequence>\d{{2}})-(?P<name>.+){re.escape(REPORT_SUFFIX)}$'
)
BODY_NAME_PATTERN = re.compile(
    r'<span\b[^>]*class=["\'][^"\']*\binfo-label\b[^"\']*["\'][^>]*>'
    r'\s*姓名\s*</span>\s*'
    r'<span\b[^>]*class=["\'][^"\']*\binfo-value\b[^"\']*\bname\b'
    r'[^"\']*["\'][^>]*>\s*([^<]+?)\s*</span>',
    re.IGNORECASE | re.DOTALL,
)
SCRIPT_SRC_PATTERN = re.compile(
    r'<script\b[^>]*\bsrc\s*=\s*(["\'])(.*?)\1[^>]*>',
    re.IGNORECASE | re.DOTALL,
)
EXTERNAL_URL_PATTERN = re.compile(
    r'(?:https?:)?//[^\s"\'<>]+',
    re.IGNORECASE,
)
SCRIPT_TAG_PATTERN = re.compile(r'<script\b', re.IGNORECASE)
SCRIPT_END_PATTERN = re.compile(r'</script\s*>', re.IGNORECASE)
CANVAS_ID_PATTERN = re.compile(
    r'<canvas\b[^>]*\bid\s*=\s*(["\'])(.*?)\1[^>]*>',
    re.IGNORECASE | re.DOTALL,
)
EXPECTED_CANVAS_IDS = ['radarChart', 'discChart', 'barChart', 'hBarChart']
FORBIDDEN_ELEMENT_PATTERN = re.compile(
    r'<\s*(?:form|iframe|object|embed|base)\b',
    re.IGNORECASE,
)
META_REFRESH_PATTERN = re.compile(
    r'<meta\b[^>]*\bhttp-equiv\s*=\s*(["\'])?\s*refresh\b',
    re.IGNORECASE | re.DOTALL,
)
EVENT_HANDLER_PATTERN = re.compile(
    r'<[^>]+\son[a-z][a-z0-9_-]*\s*=',
    re.IGNORECASE | re.DOTALL,
)
ACTIVE_CONTENT_PATTERNS = [
    re.compile(r'\bfetch\s*\(', re.IGNORECASE),
    re.compile(r'\bXMLHttpRequest\b'),
    re.compile(r'\bWebSocket\b'),
    re.compile(r'\bEventSource\b'),
    re.compile(r'\b(?:SharedWorker|Worker)\b'),
    re.compile(r'\beval\s*\(', re.IGNORECASE),
    re.compile(r'\bFunction\s*\('),
    re.compile(r'\bimport\s*\('),
    re.compile(r'\bdocument\s*\.\s*cookie\b', re.IGNORECASE),
    re.compile(r'\bdocument\s*\.\s*domain\b', re.IGNORECASE),
    re.compile(r'\b(?:localStorage|sessionStorage)\b', re.IGNORECASE),
    re.compile(r'\bdocument\s*\.\s*write(?:ln)?\s*\(', re.IGNORECASE),
    re.compile(r'\binnerHTML\b', re.IGNORECASE),
    re.compile(r'\bwindow\s*\.\s*open\s*\(', re.IGNORECASE),
    re.compile(r'\bnavigator\s*\.\s*sendBeacon\s*\(', re.IGNORECASE),
    re.compile(r'\bcreateElement\s*\(', re.IGNORECASE),
    re.compile(r'\bImage\s*\('),
    re.compile(r'\bpostMessage\s*\(', re.IGNORECASE),
    re.compile(r'\bwindow\s*\.\s*(?:top|parent)\b', re.IGNORECASE),
    re.compile(r'\b(?:top|parent)\s*(?:\.|\[)', re.IGNORECASE),
    re.compile(r'\b(?:window|document)\s*\.\s*location\b', re.IGNORECASE),
    re.compile(r'\blocation\s*(?:\.|\[|=)', re.IGNORECASE),
    re.compile(r'\bsetAttribute\s*\(\s*["\']on', re.IGNORECASE),
]


@dataclass(frozen=True)
class ParsedTalentProfile:
    sequence: str
    name: str
    original_filename: str
    content: bytes
    file_size: int
    sha256: str


@dataclass(frozen=True)
class ImportPlan:
    parsed: ParsedTalentProfile
    student: object
    existing: TalentProfileReport | None
    action: str


class Command(BaseCommand):
    help = '从受控 ZIP 归档导入指定培训期的学员人才画像 HTML。'

    def add_arguments(self, parser):
        parser.add_argument('zip_path', help='人才画像 ZIP 文件路径')
        parser.add_argument(
            '--camp',
            dest='camp_slug',
            help='培训期 slug；不填写时使用当前激活培训期',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='完成全部校验但不写文件或数据库',
        )
        parser.add_argument(
            '--replace-existing',
            action='store_true',
            help='允许替换当前培训期中内容发生变化的已有画像',
        )

    def handle(self, *args, **options):
        archive_path = Path(options['zip_path']).expanduser().resolve()
        camp = self._resolve_camp(options.get('camp_slug'))
        parsed_reports = self._read_and_validate_archive(archive_path)
        students_by_name = self._validate_roster(camp, parsed_reports)
        plans = self._build_plans(
            camp,
            parsed_reports,
            students_by_name,
            replace_existing=options['replace_existing'],
        )

        summary = self._plan_summary(plans)
        if options['dry_run']:
            self.stdout.write(self.style.SUCCESS(f'检查通过：{summary}；文件和数据库未改动。'))
            return

        applied_plans = self._apply_plans(
            camp,
            parsed_reports,
            replace_existing=options['replace_existing'],
        )
        summary = self._plan_summary(applied_plans)
        self.stdout.write(self.style.SUCCESS(f'导入完成：{summary}。'))
        self.stdout.write('安全提示：请立即删除服务器上的原始 ZIP 文件。')

    def _resolve_camp(self, camp_slug):
        if camp_slug:
            camp = TrainingCamp.objects.filter(slug=camp_slug).first()
            if not camp:
                raise CommandError(f'找不到培训期：{camp_slug}。')
            return camp

        camp = TrainingCamp.get_active()
        if not camp:
            raise CommandError('当前没有激活的培训期，请使用 --camp 指定培训期。')
        return camp

    def _read_and_validate_archive(self, archive_path):
        if archive_path.suffix.lower() != '.zip':
            raise CommandError('人才画像归档必须是 .zip 文件。')
        if not archive_path.is_file():
            raise CommandError('找不到人才画像 ZIP 文件。')

        try:
            archive = zipfile.ZipFile(archive_path)
        except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
            raise CommandError('人才画像 ZIP 无法读取或已经损坏。') from exc

        try:
            infos = archive.infolist()
            if not infos:
                raise CommandError('人才画像 ZIP 中没有文件。')
            if len(infos) > MAX_REPORT_COUNT:
                raise CommandError(f'人才画像 ZIP 内文件数不能超过 {MAX_REPORT_COUNT}。')

            parsed_reports = []
            seen_filenames = set()
            seen_sequences = set()
            seen_names = set()
            total_size = 0
            for info in infos:
                parsed = self._read_member(archive, info, total_size)
                total_size += parsed.file_size
                if total_size > MAX_ARCHIVE_UNCOMPRESSED_SIZE:
                    raise CommandError('人才画像 ZIP 解压后的总大小超过 100MB。')
                if parsed.original_filename in seen_filenames:
                    raise CommandError(f'ZIP 内存在重复文件名：{parsed.original_filename}。')
                if parsed.sequence in seen_sequences:
                    raise CommandError(f'ZIP 内存在重复编号：{parsed.sequence}。')
                if parsed.name in seen_names:
                    raise CommandError(f'ZIP 内存在重复姓名：{parsed.name}。')
                seen_filenames.add(parsed.original_filename)
                seen_sequences.add(parsed.sequence)
                seen_names.add(parsed.name)
                parsed_reports.append(parsed)
            return parsed_reports
        finally:
            archive.close()

    def _read_member(self, archive, info, current_total_size):
        normalized_member_name = info.filename.replace('\\', '/')
        member_path = PurePosixPath(normalized_member_name)
        if (
            info.is_dir()
            or member_path.is_absolute()
            or len(member_path.parts) != 1
            or member_path.name != normalized_member_name
        ):
            raise CommandError('ZIP 中只允许根目录下的 HTML 文件。')
        if member_path.suffix.lower() != '.html':
            raise CommandError(f'ZIP 中只允许 .html 文件：{info.filename}。')
        if len(info.filename) > TalentProfileReport._meta.get_field('original_filename').max_length:
            raise CommandError(f'画像文件名过长：{info.filename}。')
        if info.flag_bits & 0x1:
            raise CommandError(f'不支持加密的画像文件：{info.filename}。')
        if info.file_size <= 0 or info.file_size > MAX_REPORT_SIZE:
            raise CommandError(f'画像文件必须大于 0 且不能超过 2MB：{info.filename}。')
        if current_total_size + info.file_size > MAX_ARCHIVE_UNCOMPRESSED_SIZE:
            raise CommandError('人才画像 ZIP 解压后的总大小超过 100MB。')
        if info.file_size > max(info.compress_size, 1) * MAX_COMPRESSION_RATIO:
            raise CommandError(f'画像文件压缩比例异常：{info.filename}。')

        try:
            content = archive.read(info)
        except (OSError, RuntimeError, ValueError, zipfile.BadZipFile) as exc:
            raise CommandError(f'画像文件无法解压或校验失败：{info.filename}。') from exc
        if len(content) != info.file_size:
            raise CommandError(f'画像文件解压后大小不一致：{info.filename}。')
        if b'\x00' in content:
            raise CommandError(f'画像 HTML 包含无效的二进制内容：{info.filename}。')
        try:
            document = content.decode('utf-8-sig')
        except UnicodeDecodeError as exc:
            raise CommandError(f'画像 HTML 必须使用 UTF-8 编码：{info.filename}。') from exc
        normalized_document = document.lstrip().lower()
        if not (
            normalized_document.startswith('<!doctype html')
            or normalized_document.startswith('<html')
        ):
            raise CommandError(f'画像文件不是真实的 HTML 文档：{info.filename}。')

        filename_match = REPORT_FILENAME_PATTERN.fullmatch(info.filename)
        if not filename_match:
            raise CommandError(
                f'画像文件名必须为“编号-姓名-新员工人才画像报告.html”：{info.filename}。'
            )
        filename_name = self._normalize_name(filename_match.group('name'))
        if not filename_name:
            raise CommandError(f'画像文件名中的姓名不能为空：{info.filename}。')

        body_names = [
            self._normalize_name(html.unescape(name))
            for name in BODY_NAME_PATTERN.findall(document)
        ]
        if len(body_names) != 1 or not body_names[0]:
            raise CommandError(f'画像正文必须包含唯一且非空的姓名字段：{info.filename}。')
        if body_names[0] != filename_name:
            raise CommandError(
                f'画像正文姓名与文件名不一致：{info.filename}。'
            )

        script_sources = [
            html.unescape(match[1]).strip()
            for match in SCRIPT_SRC_PATTERN.findall(document)
        ]
        external_urls = [
            html.unescape(url).strip()
            for url in EXTERNAL_URL_PATTERN.findall(document)
        ]
        if script_sources != [ALLOWED_CHART_JS_URL] or external_urls != [ALLOWED_CHART_JS_URL]:
            raise CommandError(
                f'画像只允许唯一外链 Chart.js 4.4.1：{info.filename}。'
            )
        canvas_ids = [
            html.unescape(match[1]).strip()
            for match in CANVAS_ID_PATTERN.findall(document)
        ]
        if (
            len(SCRIPT_TAG_PATTERN.findall(document)) != 2
            or len(SCRIPT_END_PATTERN.findall(document)) != 2
            or canvas_ids != EXPECTED_CANVAS_IDS
        ):
            raise CommandError(
                f'画像脚本或图表画布结构与当前模板不一致：{info.filename}。'
            )
        if (
            FORBIDDEN_ELEMENT_PATTERN.search(document)
            or META_REFRESH_PATTERN.search(document)
            or EVENT_HANDLER_PATTERN.search(document)
            or any(pattern.search(document) for pattern in ACTIVE_CONTENT_PATTERNS)
        ):
            raise CommandError(
                f'画像包含模板不允许的主动内容：{info.filename}。'
            )

        return ParsedTalentProfile(
            sequence=filename_match.group('sequence'),
            name=filename_name,
            original_filename=info.filename,
            content=content,
            file_size=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
        )

    def _validate_roster(self, camp, parsed_reports, *, lock=False):
        queryset = (
            TrainingCampMembership.objects
            .select_related('student', 'student__profile')
            .filter(
                camp=camp,
                student__is_staff=False,
                student__is_superuser=False,
                student__profile__role=Profile.Role.STUDENT,
            )
        )
        if lock:
            queryset = queryset.select_for_update()
        memberships = list(queryset)
        memberships_by_name = defaultdict(list)
        for membership in memberships:
            normalized_name = self._normalize_name(membership.student.profile.name)
            memberships_by_name[normalized_name].append(membership)

        duplicate_names = sorted(
            name
            for name, matches in memberships_by_name.items()
            if not name or len(matches) != 1
        )
        if duplicate_names:
            labels = '、'.join(name or '（空姓名）' for name in duplicate_names)
            raise CommandError(f'培训期成员存在空姓名或同名学员，已停止导入：{labels}。')

        report_names = {report.name for report in parsed_reports}
        member_names = set(memberships_by_name)
        missing = sorted(member_names - report_names)
        extra = sorted(report_names - member_names)
        if missing or extra:
            details = []
            if missing:
                details.append(f'缺少画像：{"、".join(missing)}')
            if extra:
                details.append(f'非本培训期学员：{"、".join(extra)}')
            raise CommandError('画像名单与培训期普通学员不一致：' + '；'.join(details) + '。')

        return {
            name: matches[0].student
            for name, matches in memberships_by_name.items()
        }

    def _build_plans(
        self,
        camp,
        parsed_reports,
        students_by_name,
        *,
        replace_existing,
        lock_existing=False,
    ):
        existing_queryset = TalentProfileReport.objects.filter(
            camp=camp,
            student_id__in=[student.id for student in students_by_name.values()],
        )
        if lock_existing:
            existing_queryset = existing_queryset.select_for_update()
        existing_by_student_id = {
            report.student_id: report
            for report in existing_queryset
        }
        storage = TalentProfileReport._meta.get_field('file').storage
        plans = []
        changed_without_permission = []
        for parsed in parsed_reports:
            student = students_by_name[parsed.name]
            existing = existing_by_student_id.get(student.id)
            if not existing:
                action = 'create'
            else:
                try:
                    file_exists = bool(existing.file and storage.exists(existing.file.name))
                except (OSError, ValueError):
                    file_exists = False
                if existing.sha256 == parsed.sha256 and file_exists:
                    action = 'skip'
                elif existing.sha256 != parsed.sha256 and not replace_existing:
                    changed_without_permission.append(parsed.name)
                    action = 'replace'
                else:
                    action = 'replace'
            plans.append(ImportPlan(parsed, student, existing, action))

        if changed_without_permission:
            raise CommandError(
                '以下学员已有不同内容的画像；确认覆盖时请使用 --replace-existing：'
                + '、'.join(sorted(changed_without_permission))
                + '。'
            )
        return plans

    def _apply_plans(self, camp, parsed_reports, *, replace_existing):
        storage = TalentProfileReport._meta.get_field('file').storage
        created_file_names = []
        old_file_names = []
        try:
            with transaction.atomic():
                locked_camp = TrainingCamp.objects.select_for_update().get(pk=camp.pk)
                students_by_name = self._validate_roster(
                    locked_camp,
                    parsed_reports,
                    lock=True,
                )
                plans = self._build_plans(
                    locked_camp,
                    parsed_reports,
                    students_by_name,
                    replace_existing=replace_existing,
                    lock_existing=True,
                )
                for plan in plans:
                    if plan.action == 'skip':
                        continue
                    instance = plan.existing or TalentProfileReport(
                        camp=locked_camp,
                        student=plan.student,
                    )
                    old_name = instance.file.name if plan.existing and instance.file else ''
                    instance.file.save(
                        plan.parsed.original_filename,
                        ContentFile(plan.parsed.content),
                        save=False,
                    )
                    created_file_names.append(instance.file.name)
                    instance.original_filename = plan.parsed.original_filename
                    instance.file_size = plan.parsed.file_size
                    instance.sha256 = plan.parsed.sha256
                    instance.save()
                    if old_name and old_name != instance.file.name:
                        old_file_names.append(old_name)

                if old_file_names:
                    transaction.on_commit(
                        lambda names=tuple(old_file_names): self._delete_old_files(
                            storage,
                            names,
                        )
                    )
            return plans
        except Exception as exc:
            cleanup_errors = self._delete_files(storage, created_file_names)
            if cleanup_errors:
                self.stderr.write(
                    self.style.WARNING(
                        '导入失败，且以下本次新文件未能清理：'
                        + '、'.join(cleanup_errors)
                    )
                )
            if isinstance(exc, CommandError):
                raise
            raise CommandError('人才画像写入失败，数据库已回滚。') from exc

    @staticmethod
    def _normalize_name(value):
        return unicodedata.normalize('NFKC', str(value or '')).strip()

    @staticmethod
    def _plan_summary(plans):
        counts = {
            action: sum(plan.action == action for plan in plans)
            for action in ('create', 'replace', 'skip')
        }
        return (
            f'共 {len(plans)} 份画像，可新增 {counts["create"]} 份，'
            f'可替换 {counts["replace"]} 份，相同内容跳过 {counts["skip"]} 份'
        )

    def _delete_old_files(self, storage, names):
        cleanup_errors = self._delete_files(storage, names)
        if cleanup_errors:
            self.stderr.write(
                self.style.WARNING(
                    '画像已更新，但以下旧文件未能清理：'
                    + '、'.join(cleanup_errors)
                )
            )

    @staticmethod
    def _delete_files(storage, names):
        errors = []
        for name in dict.fromkeys(names):
            try:
                storage.delete(name)
            except Exception:
                errors.append(name)
        return errors
