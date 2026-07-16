import io
import shutil
import tempfile
import zipfile
from datetime import date, time
from pathlib import Path

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image
from rest_framework.test import APIClient

from .models import Course, CourseResource, Profile, TrainingCamp


TEST_COURSE_MATERIAL_ROOT = tempfile.mkdtemp()


@override_settings(
    COURSE_MATERIAL_ROOT=TEST_COURSE_MATERIAL_ROOT,
    COURSE_MATERIAL_USE_X_ACCEL=False,
)
class CourseMaterialApiTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_COURSE_MATERIAL_ROOT, ignore_errors=True)

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        TrainingCamp.objects.filter(is_active=True).update(is_active=False)
        self.camp = TrainingCamp.objects.create(
            name='课程资料测试营',
            slug='course-material-test',
            start_date=date(2026, 7, 16),
            end_date=date(2026, 7, 20),
            is_active=True,
        )
        self.course = Course.objects.create(
            camp=self.camp,
            title='AI 入门课',
            topic='AI',
            teacher='测试讲师',
            room='测试教室',
            date=date(2026, 7, 16),
            start_time=time(9, 0),
            end_time=time(11, 0),
        )
        self.student = User.objects.create_user(username='course-student', password='Student12345')
        self.admin = User.objects.create_user(username='course-admin', password='Admin12345', is_staff=True)
        self.admin.profile.role = Profile.Role.ADMIN
        self.admin.profile.save(update_fields=['role'])

    def image_file(self, name='思维导图.png'):
        stream = io.BytesIO()
        Image.new('RGB', (20, 12), '#ff3344').save(stream, format='PNG')
        return SimpleUploadedFile(name, stream.getvalue(), content_type='image/png')

    def pdf_file(self, name='课程讲义.pdf'):
        return SimpleUploadedFile(name, b'%PDF-1.4\ncourse material\n%%EOF', content_type='application/pdf')

    def pptx_file(self, name='课堂演示.pptx'):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('[Content_Types].xml', '<Types />')
            archive.writestr('ppt/presentation.xml', '<p:presentation />')
        return SimpleUploadedFile(
            name,
            stream.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.presentationml.presentation',
        )

    def upload_materials(self):
        self.client.force_authenticate(self.admin)
        return self.client.post(
            f'/api/courses/{self.course.pk}/materials/',
            {
                'mind_map': self.image_file(),
                'resources': [self.pdf_file(), self.pptx_file()],
            },
            format='multipart',
        )

    def test_course_list_requires_login(self):
        response = self.client.get('/api/courses/')

        self.assertEqual(response.status_code, 401)

    def test_admin_can_upload_mind_map_pdf_and_pptx(self):
        response = self.upload_materials()

        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data['has_mind_map'])
        self.assertEqual(response.data['mind_map_original_filename'], '思维导图.png')
        self.assertEqual(len(response.data['resources']), 2)
        self.assertEqual({item['file_type'] for item in response.data['resources']}, {'pdf', 'pptx'})
        self.assertTrue(all('file' not in item for item in response.data['resources']))
        self.assertNotIn('mind_map', response.data)
        self.assertTrue(Path(self.course.mind_map.storage.location).is_dir())

    def test_student_cannot_upload_or_delete_course_materials(self):
        self.client.force_authenticate(self.student)
        upload_response = self.client.post(
            f'/api/courses/{self.course.pk}/materials/',
            {'resources': [self.pdf_file()]},
            format='multipart',
        )

        self.assertEqual(upload_response.status_code, 403)

        self.upload_materials()
        resource = CourseResource.objects.get(content_type='application/pdf')
        self.client.force_authenticate(self.student)
        delete_response = self.client.delete(f'/api/course-resources/{resource.pk}/')
        self.assertEqual(delete_response.status_code, 403)
        self.assertTrue(CourseResource.objects.filter(pk=resource.pk).exists())

    def test_disguised_or_unsupported_files_are_rejected(self):
        self.client.force_authenticate(self.admin)
        fake_pdf = SimpleUploadedFile('伪装资料.pdf', b'MZ executable', content_type='application/pdf')
        fake_pptx = SimpleUploadedFile('伪装课件.pptx', b'not a zip', content_type='application/octet-stream')

        pdf_response = self.client.post(
            f'/api/courses/{self.course.pk}/materials/',
            {'resources': [fake_pdf]},
            format='multipart',
        )
        pptx_response = self.client.post(
            f'/api/courses/{self.course.pk}/materials/',
            {'resources': [fake_pptx]},
            format='multipart',
        )

        self.assertEqual(pdf_response.status_code, 400)
        self.assertEqual(pptx_response.status_code, 400)
        self.assertEqual(self.course.resources.count(), 0)

    def test_logged_in_student_can_read_files_but_anonymous_user_cannot(self):
        self.upload_materials()
        resource = CourseResource.objects.get(content_type='application/pdf')

        self.client.force_authenticate(user=None)
        anonymous_response = self.client.get(f'/api/course-resources/{resource.pk}/file/')
        self.assertEqual(anonymous_response.status_code, 401)

        self.client.force_authenticate(self.student)
        resource_response = self.client.get(f'/api/course-resources/{resource.pk}/file/')
        mind_map_response = self.client.get(f'/api/courses/{self.course.pk}/mind-map-file/')

        self.assertEqual(resource_response.status_code, 200)
        self.assertEqual(resource_response['Content-Type'], 'application/pdf')
        self.assertTrue(b''.join(resource_response.streaming_content).startswith(b'%PDF-'))
        self.assertEqual(mind_map_response.status_code, 200)
        self.assertEqual(mind_map_response['Content-Type'], 'image/png')
        self.assertGreater(len(b''.join(mind_map_response.streaming_content)), 20)

    @override_settings(COURSE_MATERIAL_USE_X_ACCEL=True)
    def test_production_download_uses_internal_nginx_redirect(self):
        self.upload_materials()
        resource = CourseResource.objects.get(content_type='application/pdf')
        self.client.force_authenticate(self.student)

        response = self.client.get(f'/api/course-resources/{resource.pk}/file/')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response['X-Accel-Redirect'].startswith('/_protected_course_files/courses/'))
        self.assertNotIn(str(TEST_COURSE_MATERIAL_ROOT), response['X-Accel-Redirect'])
        self.assertEqual(response['Cache-Control'], 'private, no-store')

    def test_admin_delete_removes_database_record_and_physical_file(self):
        self.upload_materials()
        resource = CourseResource.objects.get(content_type='application/pdf')
        stored_path = Path(resource.file.path)
        self.assertTrue(stored_path.exists())

        self.client.force_authenticate(self.admin)
        response = self.client.delete(f'/api/course-resources/{resource.pk}/')

        self.assertEqual(response.status_code, 200)
        self.assertFalse(CourseResource.objects.filter(pk=resource.pk).exists())
        self.assertFalse(stored_path.exists())
        self.assertEqual(len(response.data['resources']), 1)

    @override_settings(COURSE_RESOURCE_MAX_FILES=1)
    def test_resource_count_limit_is_enforced(self):
        self.client.force_authenticate(self.admin)

        response = self.client.post(
            f'/api/courses/{self.course.pk}/materials/',
            {'resources': [self.pdf_file('一.pdf'), self.pdf_file('二.pdf')]},
            format='multipart',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.course.resources.count(), 0)

    @override_settings(COURSE_MATERIAL_MAX_REQUEST_SIZE=10)
    def test_total_request_size_limit_is_enforced(self):
        self.client.force_authenticate(self.admin)

        response = self.client.post(
            f'/api/courses/{self.course.pk}/materials/',
            {'resources': [self.pdf_file()]},
            format='multipart',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.course.resources.count(), 0)

    def test_replacing_and_deleting_mind_map_cleans_up_old_file(self):
        self.client.force_authenticate(self.admin)
        first_response = self.client.post(
            f'/api/courses/{self.course.pk}/materials/',
            {'mind_map': self.image_file('第一版.png')},
            format='multipart',
        )
        self.assertEqual(first_response.status_code, 200)
        self.course.refresh_from_db()
        first_path = Path(self.course.mind_map.path)

        replace_response = self.client.post(
            f'/api/courses/{self.course.pk}/materials/',
            {'mind_map': self.image_file('第二版.png')},
            format='multipart',
        )
        self.assertEqual(replace_response.status_code, 200)
        self.assertFalse(first_path.exists())

        self.course.refresh_from_db()
        second_path = Path(self.course.mind_map.path)
        delete_response = self.client.delete(f'/api/courses/{self.course.pk}/mind-map/')

        self.assertEqual(delete_response.status_code, 200)
        self.assertFalse(delete_response.data['has_mind_map'])
        self.assertFalse(second_path.exists())
