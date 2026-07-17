import shutil
from datetime import timedelta
from pathlib import Path

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from .models import ChunkedUpload, Profile, TrainingCamp, Work


TEST_BASE_ROOT = Path(__file__).resolve().parent / '.test_work_html_files'
TEST_PROTECTED_ROOT = TEST_BASE_ROOT / 'protected'
TEST_CHUNK_ROOT = TEST_BASE_ROOT / 'chunks'


@override_settings(
    COURSE_MATERIAL_ROOT=TEST_PROTECTED_ROOT,
    COURSE_MATERIAL_USE_X_ACCEL=False,
    WORK_UPLOAD_CHUNK_DIR=TEST_CHUNK_ROOT,
)
class WorkHtmlUploadTests(APITestCase):
    html = b'<!doctype html><html><head><title>Demo</title></head><body><script>console.log(1)</script></body></html>'

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        shutil.rmtree(TEST_BASE_ROOT, ignore_errors=True)
        TEST_PROTECTED_ROOT.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_BASE_ROOT, ignore_errors=True)

    def setUp(self):
        TrainingCamp.objects.update(is_active=False)
        now = timezone.now()
        self.camp = TrainingCamp.objects.create(
            name='HTML upload test',
            slug='html-upload-test',
            start_date=now.date(),
            end_date=(now + timedelta(days=3)).date(),
            submission_starts_at=now - timedelta(hours=1),
            submission_ends_at=now + timedelta(hours=1),
            is_active=True,
        )
        self.student = User.objects.create_user(username='html-student', password='Pass12345!')
        self.other_student = User.objects.create_user(username='html-other', password='Pass12345!')
        self.admin = User.objects.create_user(username='html-admin', password='Pass12345!', is_staff=True)
        self.admin.profile.role = Profile.Role.ADMIN
        self.admin.profile.save(update_fields=['role'])
        self.client.force_authenticate(self.student)

    def complete_html_upload(self, *, file_name='demo.html', content=None):
        payload = self.html if content is None else content
        init_response = self.client.post('/api/uploads/init/', {
            'file_name': file_name,
            'content_type': 'text/html',
            'total_size': len(payload),
            'total_chunks': 1,
        }, format='json')
        self.assertEqual(init_response.status_code, status.HTTP_201_CREATED, init_response.data)
        upload_id = init_response.data['upload_id']
        chunk_response = self.client.post(
            f'/api/uploads/{upload_id}/chunk/',
            {'index': 0, 'chunk': SimpleUploadedFile('part0', payload)},
            format='multipart',
        )
        self.assertEqual(chunk_response.status_code, status.HTTP_200_OK, chunk_response.data)
        complete_response = self.client.post(f'/api/uploads/{upload_id}/complete/')
        return upload_id, complete_response

    def publish_html_work(self):
        upload_id, complete_response = self.complete_html_upload()
        self.assertEqual(complete_response.status_code, status.HTTP_200_OK, complete_response.data)
        response = self.client.post('/api/works/', {
            'title': 'Interactive HTML demo',
            'work_type': Work.WorkType.AI,
            'description': 'A complete HTML work used for secure download testing.',
            'upload_id': upload_id,
        }, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        return Work.objects.get(pk=response.data['id']), response

    def test_html_upload_is_never_exposed_through_public_media(self):
        upload_id, complete_response = self.complete_html_upload()
        self.assertEqual(complete_response.status_code, status.HTTP_200_OK, complete_response.data)
        self.assertEqual(complete_response.data['file'], '')
        self.assertTrue(complete_response.data['protected'])

        upload = ChunkedUpload.objects.get(upload_id=upload_id)
        self.assertFalse(upload.file)
        self.assertTrue(upload.protected_file)
        self.assertTrue(upload.protected_file.storage.exists(upload.protected_file.name))

    def test_student_can_publish_html_and_protected_file_is_transferred(self):
        work, response = self.publish_html_work()
        self.assertEqual(work.media_type, Work.MediaType.HTML)
        self.assertFalse(work.attachment)
        self.assertTrue(work.protected_attachment)
        self.assertTrue(response.data['has_attachment'])
        self.assertIsNone(response.data['attachment'])

        upload = ChunkedUpload.objects.get(owner=self.student)
        self.assertEqual(upload.status, ChunkedUpload.Status.CONSUMED)
        self.assertFalse(upload.protected_file)

    def test_approved_html_can_only_be_downloaded_through_authenticated_endpoint(self):
        work, _ = self.publish_html_work()
        work.status = Work.Status.APPROVED
        work.save(update_fields=['status'])

        response = self.client.get(f'/api/works/{work.pk}/file/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/octet-stream')
        self.assertIn('attachment;', response['Content-Disposition'])
        self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
        self.assertIn('sandbox', response['Content-Security-Policy'])
        self.assertEqual(b''.join(response.streaming_content), self.html)

        self.client.force_authenticate(user=None)
        anonymous_response = self.client.get(f'/api/works/{work.pk}/file/')
        self.assertEqual(anonymous_response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_other_student_cannot_download_pending_html(self):
        work, _ = self.publish_html_work()
        self.client.force_authenticate(self.other_student)
        response = self.client.get(f'/api/works/{work.pk}/file/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        self.client.force_authenticate(self.admin)
        admin_response = self.client.get(f'/api/works/{work.pk}/file/')
        self.assertEqual(admin_response.status_code, status.HTTP_200_OK)

    def test_invalid_html_content_is_rejected_before_protected_storage(self):
        upload_id, response = self.complete_html_upload(content=b'not an html document')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        upload = ChunkedUpload.objects.get(upload_id=upload_id)
        self.assertEqual(upload.status, ChunkedUpload.Status.UPLOADING)
        self.assertFalse(upload.protected_file)

    def test_html_filename_and_size_are_validated(self):
        wrong_extension = self.client.post('/api/uploads/init/', {
            'file_name': 'demo.txt',
            'content_type': 'text/html',
            'total_size': len(self.html),
            'total_chunks': 1,
        }, format='json')
        self.assertEqual(wrong_extension.status_code, status.HTTP_400_BAD_REQUEST)

        with override_settings(WORK_HTML_MAX_UPLOAD_SIZE=10):
            too_large = self.client.post('/api/uploads/init/', {
                'file_name': 'demo.html',
                'content_type': 'text/html',
                'total_size': 11,
                'total_chunks': 1,
            }, format='json')
        self.assertEqual(too_large.status_code, status.HTTP_400_BAD_REQUEST)

    def test_direct_html_attachment_is_rejected_to_avoid_public_media_storage(self):
        response = self.client.post('/api/works/', {
            'title': 'Unsafe direct HTML',
            'work_type': Work.WorkType.AI,
            'description': 'This upload must be rejected before it reaches public media storage.',
            'attachment': SimpleUploadedFile('unsafe.html', self.html, content_type='text/html'),
        }, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Work.objects.filter(title='Unsafe direct HTML').exists())
