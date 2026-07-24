import hashlib
import html
import io
import shutil
import tempfile
import uuid
import zipfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from rest_framework.test import APIClient

from .management.commands.import_talent_profiles import ALLOWED_CHART_JS_URL, Command
from .models import (
    Profile,
    TalentProfileReport,
    TrainingCamp,
    TrainingCampMembership,
)


TEST_BASE_ROOT = Path(tempfile.mkdtemp())
TEST_PROTECTED_ROOT = TEST_BASE_ROOT / 'protected'
TEST_ARCHIVE_ROOT = TEST_BASE_ROOT / 'archives'


def tearDownModule():
    shutil.rmtree(TEST_BASE_ROOT, ignore_errors=True)


def talent_profile_html(
    name,
    *,
    body_name=None,
    marker='',
    extra_external='',
    active_code='',
):
    filename_name = html.escape(name)
    rendered_body_name = html.escape(body_name if body_name is not None else name)
    return (
        '<!doctype html><html lang="zh-CN"><head><meta charset="UTF-8">'
        f'<title>{filename_name} · 新员工人才画像报告</title>'
        f'<script src="{ALLOWED_CHART_JS_URL}"></script>'
        '</head><body>'
        '<div class="info-item">'
        '<span class="info-label">姓名</span>'
        f'<span class="info-value name">{rendered_body_name}</span>'
        '</div>'
        '<canvas id="radarChart"></canvas>'
        '<canvas id="discChart"></canvas>'
        '<canvas id="barChart"></canvas>'
        '<canvas id="hBarChart"></canvas>'
        f'{extra_external}<script>window.reportMarker={marker!r};{active_code}</script>'
        '</body></html>'
    ).encode('utf-8')


def save_report(camp, student, content, original_filename):
    report = TalentProfileReport(
        camp=camp,
        student=student,
        original_filename=original_filename,
        file_size=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
    )
    report.file.save(original_filename, ContentFile(content), save=False)
    report.save()
    return report


@override_settings(
    COURSE_MATERIAL_ROOT=TEST_PROTECTED_ROOT,
    COURSE_MATERIAL_USE_X_ACCEL=False,
)
class TalentProfileApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        TrainingCamp.objects.filter(is_active=True).update(is_active=False)
        self.old_camp = TrainingCamp.objects.create(
            name='往期培训',
            slug='talent-profile-old',
            start_date='2026-06-01',
            end_date='2026-06-05',
            is_active=False,
        )
        self.camp = TrainingCamp.objects.create(
            name='当前培训',
            slug='talent-profile-current',
            start_date='2026-07-01',
            end_date='2026-07-05',
            is_active=True,
        )
        self.student = self.create_student('student-a', '学员甲')
        self.other_student = self.create_student('student-b', '学员乙')
        self.outsider = self.create_student('student-outside', '外部学员')
        TrainingCampMembership.objects.create(camp=self.camp, student=self.student)
        TrainingCampMembership.objects.create(camp=self.camp, student=self.other_student)
        self.admin = User.objects.create_user(
            username='talent-admin',
            password='Admin12345',
            is_staff=True,
        )
        self.admin.profile.role = Profile.Role.ADMIN
        self.admin.profile.save(update_fields=['role'])

    @staticmethod
    def create_student(username, name):
        user = User.objects.create_user(username=username, password='Student12345')
        user.profile.name = name
        user.profile.role = Profile.Role.STUDENT
        user.profile.save(update_fields=['name', 'role'])
        return user

    def test_student_gets_only_own_current_camp_metadata_and_attachment(self):
        own_content = talent_profile_html('学员甲')
        other_content = talent_profile_html('学员乙')
        own_report = save_report(
            self.camp,
            self.student,
            own_content,
            '01-学员甲-新员工人才画像报告.html',
        )
        save_report(
            self.camp,
            self.other_student,
            other_content,
            '02-学员乙-新员工人才画像报告.html',
        )
        self.client.force_authenticate(self.student)

        metadata_response = self.client.get('/api/me/talent-profile/')
        file_response = self.client.get('/api/me/talent-profile/file/')

        self.assertEqual(metadata_response.status_code, 200)
        self.assertEqual(
            set(metadata_response.data),
            {'available', 'original_filename', 'file_size', 'updated_at'},
        )
        self.assertTrue(metadata_response.data['available'])
        self.assertEqual(metadata_response.data['original_filename'], own_report.original_filename)
        self.assertEqual(metadata_response.data['file_size'], len(own_content))
        self.assertEqual(metadata_response['Cache-Control'], 'private, no-store')
        self.assertEqual(metadata_response['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(file_response.status_code, 200)
        self.assertEqual(file_response['Content-Type'], 'application/octet-stream')
        self.assertIn('attachment;', file_response['Content-Disposition'])
        self.assertEqual(file_response['Cache-Control'], 'private, no-store')
        self.assertEqual(file_response['X-Content-Type-Options'], 'nosniff')
        self.assertIn('sandbox', file_response['Content-Security-Policy'])
        returned_content = b''.join(file_response.streaming_content)
        self.assertEqual(returned_content, own_content)
        self.assertNotEqual(returned_content, other_content)
        self.assertTrue(own_report.file.name.startswith(f'talent-profiles/{self.camp.id}/'))
        self.assertNotIn('学员甲', own_report.file.name)
        self.assertNotIn(own_report.original_filename, own_report.file.name)

    def test_endpoints_reject_anonymous_admin_and_non_member(self):
        for path in ('/api/me/talent-profile/', '/api/me/talent-profile/file/'):
            anonymous_response = self.client.get(path)
            self.assertEqual(anonymous_response.status_code, 401)

            self.client.force_authenticate(self.admin)
            admin_response = self.client.get(path)
            self.assertEqual(admin_response.status_code, 403)

            self.client.force_authenticate(self.outsider)
            outsider_response = self.client.get(path)
            self.assertEqual(outsider_response.status_code, 403)

            self.client.force_authenticate(user=None)

    def test_missing_active_camp_report_and_physical_file_return_404(self):
        self.client.force_authenticate(self.student)
        no_report_response = self.client.get('/api/me/talent-profile/')
        self.assertEqual(no_report_response.status_code, 404)

        report = save_report(
            self.camp,
            self.student,
            talent_profile_html('学员甲'),
            '01-学员甲-新员工人才画像报告.html',
        )
        report.file.storage.delete(report.file.name)
        missing_file_response = self.client.get('/api/me/talent-profile/file/')
        self.assertEqual(missing_file_response.status_code, 404)

        self.camp.is_active = False
        self.camp.save(update_fields=['is_active'])
        no_camp_response = self.client.get('/api/me/talent-profile/')
        self.assertEqual(no_camp_response.status_code, 404)

    def test_report_from_another_camp_is_not_exposed(self):
        TrainingCampMembership.objects.create(camp=self.old_camp, student=self.student)
        old_content = talent_profile_html('学员甲', marker='old')
        save_report(
            self.old_camp,
            self.student,
            old_content,
            '01-学员甲-新员工人才画像报告.html',
        )
        self.client.force_authenticate(self.student)

        response = self.client.get('/api/me/talent-profile/file/')

        self.assertEqual(response.status_code, 404)

    @override_settings(COURSE_MATERIAL_USE_X_ACCEL=True)
    def test_production_file_response_uses_internal_redirect(self):
        report = save_report(
            self.camp,
            self.student,
            talent_profile_html('学员甲'),
            '01-学员甲-新员工人才画像报告.html',
        )
        self.client.force_authenticate(self.student)

        response = self.client.get('/api/me/talent-profile/file/')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            response['X-Accel-Redirect'].startswith('/_protected_course_files/talent-profiles/')
        )
        self.assertNotIn(str(TEST_PROTECTED_ROOT), response['X-Accel-Redirect'])
        self.assertEqual(response['Content-Type'], 'application/octet-stream')
        self.assertIn('attachment;', response['Content-Disposition'])
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        self.assertTrue(report.file.storage.exists(report.file.name))

    def test_deleting_report_removes_physical_file(self):
        report = save_report(
            self.camp,
            self.student,
            talent_profile_html('学员甲'),
            '01-学员甲-新员工人才画像报告.html',
        )
        storage = report.file.storage
        stored_name = report.file.name
        self.assertTrue(storage.exists(stored_name))

        report.delete()

        self.assertFalse(storage.exists(stored_name))

    def test_database_rejects_two_reports_for_same_camp_and_student(self):
        save_report(
            self.camp,
            self.student,
            talent_profile_html('学员甲'),
            '01-学员甲-新员工人才画像报告.html',
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            TalentProfileReport.objects.create(
                camp=self.camp,
                student=self.student,
                file='talent-profiles/duplicate.html',
                original_filename='duplicate.html',
                file_size=1,
                sha256='0' * 64,
            )


@override_settings(
    COURSE_MATERIAL_ROOT=TEST_PROTECTED_ROOT,
    COURSE_MATERIAL_USE_X_ACCEL=False,
)
class ImportTalentProfilesTests(TransactionTestCase):
    def setUp(self):
        TEST_ARCHIVE_ROOT.mkdir(parents=True, exist_ok=True)
        TrainingCamp.objects.filter(is_active=True).update(is_active=False)
        self.camp = TrainingCamp.objects.create(
            name='画像导入培训期',
            slug='talent-import-current',
            start_date='2026-07-01',
            end_date='2026-07-05',
            is_active=True,
        )
        self.first = self.create_member('import-first', '学员甲')
        self.second = self.create_member('import-second', '学员乙')

    def tearDown(self):
        shutil.rmtree(TEST_PROTECTED_ROOT, ignore_errors=True)
        shutil.rmtree(TEST_ARCHIVE_ROOT, ignore_errors=True)
        super().tearDown()

    def create_member(self, username, name, *, camp=None):
        user = User.objects.create_user(username=username, password='Student12345')
        user.profile.name = name
        user.profile.role = Profile.Role.STUDENT
        user.profile.save(update_fields=['name', 'role'])
        TrainingCampMembership.objects.create(camp=camp or self.camp, student=user)
        return user

    def make_archive(self, entries=None):
        if entries is None:
            entries = [
                ('01-学员甲-新员工人才画像报告.html', talent_profile_html('学员甲')),
                ('02-学员乙-新员工人才画像报告.html', talent_profile_html('学员乙')),
            ]
        archive_path = TEST_ARCHIVE_ROOT / f'{uuid.uuid4().hex}.zip'
        with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as archive:
            for filename, content in entries:
                archive.writestr(filename, content)
        return archive_path

    @staticmethod
    def stored_html_files():
        if not TEST_PROTECTED_ROOT.exists():
            return []
        return list(TEST_PROTECTED_ROOT.rglob('*.html'))

    def test_dry_run_then_import_store_complete_valid_roster(self):
        archive_path = self.make_archive()
        dry_run_output = io.StringIO()

        call_command(
            'import_talent_profiles',
            archive_path,
            dry_run=True,
            stdout=dry_run_output,
        )

        self.assertIn('检查通过', dry_run_output.getvalue())
        self.assertEqual(TalentProfileReport.objects.count(), 0)
        self.assertEqual(self.stored_html_files(), [])

        call_command('import_talent_profiles', archive_path, stdout=io.StringIO())

        reports = list(TalentProfileReport.objects.order_by('student__profile__name'))
        self.assertEqual(len(reports), 2)
        self.assertEqual({report.student_id for report in reports}, {self.first.id, self.second.id})
        self.assertTrue(all(report.camp_id == self.camp.id for report in reports))
        self.assertEqual(len(self.stored_html_files()), 2)
        for report in reports:
            with report.file.open('rb') as source:
                content = source.read()
            self.assertEqual(report.file_size, len(content))
            self.assertEqual(report.sha256, hashlib.sha256(content).hexdigest())
            self.assertNotIn(report.student.profile.name, report.file.name)

    def test_explicit_missing_name_supports_dry_run_and_import_with_warning(self):
        self.second.profile.name = ' Ａlice '
        self.second.profile.save(update_fields=['name'])
        archive_path = self.make_archive([
            ('01-学员甲-新员工人才画像报告.html', talent_profile_html('学员甲')),
        ])
        dry_run_output = io.StringIO()
        dry_run_errors = io.StringIO()

        call_command(
            'import_talent_profiles',
            archive_path,
            '--allow-missing-name',
            ' Alice ',
            '--dry-run',
            stdout=dry_run_output,
            stderr=dry_run_errors,
        )

        self.assertIn('检查通过', dry_run_output.getvalue())
        self.assertIn('警告', dry_run_errors.getvalue())
        self.assertIn('Alice', dry_run_errors.getvalue())
        self.assertEqual(TalentProfileReport.objects.count(), 0)
        self.assertEqual(self.stored_html_files(), [])

        import_output = io.StringIO()
        import_errors = io.StringIO()
        call_command(
            'import_talent_profiles',
            archive_path,
            allowed_missing_names=[' Alice '],
            stdout=import_output,
            stderr=import_errors,
        )

        self.assertIn('导入完成', import_output.getvalue())
        self.assertIn('警告', import_errors.getvalue())
        self.assertIn('Alice', import_errors.getvalue())
        report = TalentProfileReport.objects.get(camp=self.camp)
        self.assertEqual(report.student_id, self.first.id)
        self.assertFalse(
            TalentProfileReport.objects.filter(
                camp=self.camp,
                student=self.second,
            ).exists()
        )
        self.assertEqual(len(self.stored_html_files()), 1)

    def test_missing_name_parameter_rejects_unknown_student(self):
        archive_path = self.make_archive([
            ('01-学员甲-新员工人才画像报告.html', talent_profile_html('学员甲')),
        ])

        with self.assertRaises(CommandError):
            call_command(
                'import_talent_profiles',
                archive_path,
                allowed_missing_names=['不存在学员'],
                stdout=io.StringIO(),
            )

        self.assertEqual(TalentProfileReport.objects.count(), 0)
        self.assertEqual(self.stored_html_files(), [])

    def test_missing_name_parameter_rejects_name_already_in_zip(self):
        archive_path = self.make_archive()

        with self.assertRaises(CommandError):
            call_command(
                'import_talent_profiles',
                archive_path,
                allowed_missing_names=[' 学员乙 '],
                stdout=io.StringIO(),
            )

        self.assertEqual(TalentProfileReport.objects.count(), 0)
        self.assertEqual(self.stored_html_files(), [])

    def test_missing_name_parameter_must_cover_every_missing_member(self):
        third = self.create_member('import-third', '学员丙')
        archive_path = self.make_archive([
            ('01-学员甲-新员工人才画像报告.html', talent_profile_html('学员甲')),
        ])

        with self.assertRaises(CommandError) as raised:
            call_command(
                'import_talent_profiles',
                archive_path,
                allowed_missing_names=['学员乙'],
                stdout=io.StringIO(),
            )

        self.assertIn(third.profile.name, str(raised.exception))
        self.assertEqual(TalentProfileReport.objects.count(), 0)
        self.assertEqual(self.stored_html_files(), [])

    def test_missing_name_parameter_rejects_normalized_duplicates(self):
        archive_path = self.make_archive([
            ('01-学员甲-新员工人才画像报告.html', talent_profile_html('学员甲')),
        ])

        with self.assertRaises(CommandError):
            call_command(
                'import_talent_profiles',
                archive_path,
                allowed_missing_names=['学员乙', ' 学员乙 '],
                stdout=io.StringIO(),
            )

        self.assertEqual(TalentProfileReport.objects.count(), 0)
        self.assertEqual(self.stored_html_files(), [])

    def test_invalid_archive_or_roster_fails_before_any_write(self):
        cases = {
            'body-name-mismatch': [
                (
                    '01-学员甲-新员工人才画像报告.html',
                    talent_profile_html('学员甲', body_name='学员乙'),
                ),
                ('02-学员乙-新员工人才画像报告.html', talent_profile_html('学员乙')),
            ],
            'missing-member': [
                ('01-学员甲-新员工人才画像报告.html', talent_profile_html('学员甲')),
            ],
            'extra-member': [
                ('01-学员甲-新员工人才画像报告.html', talent_profile_html('学员甲')),
                ('02-学员乙-新员工人才画像报告.html', talent_profile_html('学员乙')),
                ('03-学员丙-新员工人才画像报告.html', talent_profile_html('学员丙')),
            ],
            'unexpected-external-url': [
                (
                    '01-学员甲-新员工人才画像报告.html',
                    talent_profile_html(
                        '学员甲',
                        extra_external='<img src="https://example.test/leak.png">',
                    ),
                ),
                ('02-学员乙-新员工人才画像报告.html', talent_profile_html('学员乙')),
            ],
            'nested-member': [
                ('nested/01-学员甲-新员工人才画像报告.html', talent_profile_html('学员甲')),
                ('02-学员乙-新员工人才画像报告.html', talent_profile_html('学员乙')),
            ],
            'active-network-content': [
                (
                    '01-学员甲-新员工人才画像报告.html',
                    talent_profile_html(
                        '学员甲',
                        active_code='fetch("/api/me/");',
                    ),
                ),
                ('02-学员乙-新员工人才画像报告.html', talent_profile_html('学员乙')),
            ],
            'forbidden-form': [
                (
                    '01-学员甲-新员工人才画像报告.html',
                    talent_profile_html(
                        '学员甲',
                        extra_external='<form action="/api/me/"></form>',
                    ),
                ),
                ('02-学员乙-新员工人才画像报告.html', talent_profile_html('学员乙')),
            ],
            'unexpected-template-shape': [
                (
                    '01-学员甲-新员工人才画像报告.html',
                    talent_profile_html('学员甲').replace(
                        b'<canvas id="hBarChart"></canvas>',
                        b'',
                    ),
                ),
                ('02-学员乙-新员工人才画像报告.html', talent_profile_html('学员乙')),
            ],
        }

        for label, entries in cases.items():
            with self.subTest(label=label):
                archive_path = self.make_archive(entries)
                with self.assertRaises(CommandError):
                    call_command('import_talent_profiles', archive_path, stdout=io.StringIO())
                self.assertEqual(TalentProfileReport.objects.count(), 0)
                self.assertEqual(self.stored_html_files(), [])

    def test_duplicate_member_name_fails_closed(self):
        self.second.profile.name = '学员甲'
        self.second.profile.save(update_fields=['name'])
        archive_path = self.make_archive([
            ('01-学员甲-新员工人才画像报告.html', talent_profile_html('学员甲')),
        ])

        with self.assertRaises(CommandError):
            call_command('import_talent_profiles', archive_path, stdout=io.StringIO())

        self.assertEqual(TalentProfileReport.objects.count(), 0)
        self.assertEqual(self.stored_html_files(), [])

    def test_nfkc_normalized_names_match_without_changing_runtime_identity(self):
        self.first.profile.name = 'Ａlice'
        self.first.profile.save(update_fields=['name'])
        archive_path = self.make_archive([
            ('01-Alice-新员工人才画像报告.html', talent_profile_html('Alice')),
            ('02-学员乙-新员工人才画像报告.html', talent_profile_html('学员乙')),
        ])

        call_command('import_talent_profiles', archive_path, stdout=io.StringIO())

        report = TalentProfileReport.objects.get(camp=self.camp, student=self.first)
        self.assertEqual(report.original_filename, '01-Alice-新员工人才画像报告.html')
        self.assertEqual(report.student_id, self.first.id)

    def test_write_phase_rebuilds_plans_after_concurrent_state_change(self):
        archive_path = self.make_archive()
        original_apply_plans = Command._apply_plans

        def add_same_reports_before_locked_recheck(
            command,
            camp,
            parsed_reports,
            *,
            replace_existing,
            allowed_missing_names,
        ):
            students = {
                user.profile.name: user
                for user in (self.first, self.second)
            }
            for parsed in parsed_reports:
                save_report(
                    camp,
                    students[parsed.name],
                    parsed.content,
                    parsed.original_filename,
                )
            return original_apply_plans(
                command,
                camp,
                parsed_reports,
                replace_existing=replace_existing,
                allowed_missing_names=allowed_missing_names,
            )

        output = io.StringIO()
        with patch.object(
            Command,
            '_apply_plans',
            new=add_same_reports_before_locked_recheck,
        ):
            call_command('import_talent_profiles', archive_path, stdout=output)

        self.assertIn('相同内容跳过 2 份', output.getvalue())
        self.assertEqual(TalentProfileReport.objects.count(), 2)
        self.assertEqual(len(self.stored_html_files()), 2)

    def test_missing_name_exception_is_revalidated_inside_transaction(self):
        archive_path = self.make_archive([
            ('01-学员甲-新员工人才画像报告.html', talent_profile_html('学员甲')),
        ])
        original_apply_plans = Command._apply_plans

        def add_unlisted_member_before_locked_recheck(
            command,
            camp,
            parsed_reports,
            *,
            replace_existing,
            allowed_missing_names,
        ):
            self.create_member('import-late-member', '学员丙', camp=camp)
            return original_apply_plans(
                command,
                camp,
                parsed_reports,
                replace_existing=replace_existing,
                allowed_missing_names=allowed_missing_names,
            )

        with patch.object(
            Command,
            '_apply_plans',
            new=add_unlisted_member_before_locked_recheck,
        ):
            with self.assertRaises(CommandError) as raised:
                call_command(
                    'import_talent_profiles',
                    archive_path,
                    allowed_missing_names=['学员乙'],
                    stdout=io.StringIO(),
                )

        self.assertIn('学员丙', str(raised.exception))
        self.assertEqual(TalentProfileReport.objects.count(), 0)
        self.assertEqual(self.stored_html_files(), [])

    def test_same_hash_is_idempotent_and_changed_content_requires_replace(self):
        first_archive = self.make_archive()
        call_command('import_talent_profiles', first_archive, stdout=io.StringIO())
        original_reports = {
            report.student_id: (report.sha256, report.file.name)
            for report in TalentProfileReport.objects.all()
        }

        second_output = io.StringIO()
        call_command('import_talent_profiles', first_archive, stdout=second_output)
        self.assertIn('相同内容跳过 2 份', second_output.getvalue())
        self.assertEqual(
            {
                report.student_id: (report.sha256, report.file.name)
                for report in TalentProfileReport.objects.all()
            },
            original_reports,
        )

        changed_archive = self.make_archive([
            (
                '01-学员甲-新员工人才画像报告.html',
                talent_profile_html('学员甲', marker='changed'),
            ),
            ('02-学员乙-新员工人才画像报告.html', talent_profile_html('学员乙')),
        ])
        with self.assertRaises(CommandError):
            call_command('import_talent_profiles', changed_archive, stdout=io.StringIO())
        self.assertEqual(
            {
                report.student_id: (report.sha256, report.file.name)
                for report in TalentProfileReport.objects.all()
            },
            original_reports,
        )

        call_command(
            'import_talent_profiles',
            changed_archive,
            replace_existing=True,
            stdout=io.StringIO(),
        )

        changed_report = TalentProfileReport.objects.get(student=self.first)
        unchanged_report = TalentProfileReport.objects.get(student=self.second)
        self.assertNotEqual(changed_report.sha256, original_reports[self.first.id][0])
        self.assertNotEqual(changed_report.file.name, original_reports[self.first.id][1])
        self.assertFalse(changed_report.file.storage.exists(original_reports[self.first.id][1]))
        self.assertEqual(
            (unchanged_report.sha256, unchanged_report.file.name),
            original_reports[self.second.id],
        )
        self.assertEqual(len(self.stored_html_files()), 2)

    def test_database_failure_rolls_back_records_and_cleans_new_files(self):
        archive_path = self.make_archive()
        original_save = TalentProfileReport.save
        save_count = 0

        def fail_second_save(instance, *args, **kwargs):
            nonlocal save_count
            save_count += 1
            if save_count == 2:
                raise RuntimeError('simulated database failure')
            return original_save(instance, *args, **kwargs)

        with patch.object(TalentProfileReport, 'save', new=fail_second_save):
            with self.assertRaises(CommandError):
                call_command('import_talent_profiles', archive_path, stdout=io.StringIO())

        self.assertEqual(TalentProfileReport.objects.count(), 0)
        self.assertEqual(self.stored_html_files(), [])

    def test_camp_option_imports_the_explicit_inactive_camp(self):
        inactive_camp = TrainingCamp.objects.create(
            name='指定往期',
            slug='talent-import-explicit',
            start_date='2026-06-01',
            end_date='2026-06-05',
            is_active=False,
        )
        TrainingCampMembership.objects.create(camp=inactive_camp, student=self.first)
        TrainingCampMembership.objects.create(camp=inactive_camp, student=self.second)
        archive_path = self.make_archive()

        call_command(
            'import_talent_profiles',
            archive_path,
            camp_slug=inactive_camp.slug,
            stdout=io.StringIO(),
        )

        self.assertEqual(TalentProfileReport.objects.filter(camp=inactive_camp).count(), 2)
        self.assertEqual(TalentProfileReport.objects.filter(camp=self.camp).count(), 0)
