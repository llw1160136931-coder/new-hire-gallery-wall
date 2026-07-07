import shutil
import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .models import ChunkedUpload, Profile, Work


TEST_MEDIA_ROOT = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class WorkApiTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.client = APIClient()
        self.student = User.objects.create_user(username='student', password='Student12345')
        self.other = User.objects.create_user(username='other', password='Other12345')
        self.admin = User.objects.create_user(username='admin', password='Admin12345', is_staff=True)
        self.admin.profile.role = Profile.Role.ADMIN
        self.admin.profile.save(update_fields=['role'])

    def tiny_image(self, name='work.gif'):
        return SimpleUploadedFile(
            name,
            b'GIF87a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;',
            content_type='image/gif',
        )

    def test_student_can_upload_real_work_image(self):
        self.client.force_authenticate(self.student)

        response = self.client.post(
            '/api/works/',
            {
                'title': '上传图片作品',
                'work_type': Work.WorkType.AI,
                'description': '这是一份带真实图片文件的作品。',
                'link': 'https://example.com/work',
                'image': self.tiny_image(),
            },
            format='multipart',
        )

        self.assertEqual(response.status_code, 201)
        work = Work.objects.get(title='上传图片作品')
        self.assertEqual(work.status, Work.Status.PENDING)
        self.assertTrue(work.image.name.startswith('works/'))

    def test_student_can_upload_pdf_in_chunks_and_publish_work(self):
        self.client.force_authenticate(self.student)
        content = b'%PDF-1.4\nnew hire gallery wall\n%%EOF'

        init_response = self.client.post('/api/uploads/init/', {
            'file_name': 'demo.pdf',
            'content_type': 'application/pdf',
            'total_size': len(content),
            'total_chunks': 2,
        }, format='json')
        self.assertEqual(init_response.status_code, 201)
        upload_id = init_response.data['upload_id']

        first_chunk = SimpleUploadedFile('demo.part0', content[:12], content_type='application/octet-stream')
        second_chunk = SimpleUploadedFile('demo.part1', content[12:], content_type='application/octet-stream')
        self.assertEqual(self.client.post(
            f'/api/uploads/{upload_id}/chunk/',
            {'index': 0, 'chunk': first_chunk},
            format='multipart',
        ).status_code, 200)
        self.assertEqual(self.client.post(
            f'/api/uploads/{upload_id}/chunk/',
            {'index': 1, 'chunk': second_chunk},
            format='multipart',
        ).status_code, 200)

        complete_response = self.client.post(f'/api/uploads/{upload_id}/complete/')
        self.assertEqual(complete_response.status_code, 200)
        upload = ChunkedUpload.objects.get(upload_id=upload_id)
        self.assertEqual(upload.status, ChunkedUpload.Status.COMPLETED)
        self.assertTrue(upload.file.name.startswith('works/files/'))

        work_response = self.client.post('/api/works/', {
            'title': 'PDF 培训手册',
            'work_type': Work.WorkType.TRAINING,
            'description': '通过切片上传发布的 PDF。',
            'upload_id': upload_id,
        }, format='multipart')

        self.assertEqual(work_response.status_code, 201)
        work = Work.objects.get(title='PDF 培训手册')
        self.assertEqual(work.media_type, Work.MediaType.PDF)
        self.assertEqual(work.content_type, 'application/pdf')
        self.assertEqual(work.file_size, len(content))
        self.assertTrue(work.attachment.name.startswith('works/files/'))

    def test_upload_init_rejects_file_larger_than_500mb(self):
        self.client.force_authenticate(self.student)

        response = self.client.post('/api/uploads/init/', {
            'file_name': 'too-big.mp4',
            'content_type': 'video/mp4',
            'total_size': 500 * 1024 * 1024 + 1,
            'total_chunks': 101,
        }, format='json')

        self.assertEqual(response.status_code, 400)

    def test_search_returns_backend_work_and_profile_results(self):
        self.client.force_authenticate(self.student)
        self.student.profile.name = '林小夏'
        self.student.profile.school = '浙江大学'
        self.student.profile.save(update_fields=['name', 'school'])
        Work.objects.create(
            author=self.student,
            title='AI 入职欢迎海报',
            work_type=Work.WorkType.AI,
            description='搜索接口应该能找到这份作品。',
            status=Work.Status.APPROVED,
        )

        response = self.client.get('/api/search/?q=林小夏')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['profiles'][0]['name'], '林小夏')
        self.assertEqual(response.data['works'][0]['title'], 'AI 入职欢迎海报')

    def test_rejected_work_can_be_edited_and_resubmitted_by_owner(self):
        work = Work.objects.create(
            author=self.student,
            title='旧标题',
            work_type=Work.WorkType.TRAINING,
            description='旧介绍',
            status=Work.Status.REJECTED,
            reject_reason='介绍不完整',
            reviewed_by=self.admin,
        )
        self.client.force_authenticate(self.student)

        response = self.client.patch(
            f'/api/works/{work.id}/',
            {
                'title': '修改后的标题',
                'work_type': Work.WorkType.TRAINING,
                'description': '补充完整后的介绍。',
                'link': 'https://example.com/resubmit',
                'image': self.tiny_image('resubmit.gif'),
            },
            format='multipart',
        )

        self.assertEqual(response.status_code, 200)
        work.refresh_from_db()
        self.assertEqual(work.title, '修改后的标题')
        self.assertEqual(work.status, Work.Status.PENDING)
        self.assertEqual(work.reject_reason, '')
        self.assertIsNone(work.reviewed_by)
        self.assertTrue(work.image.name.startswith('works/'))

    def test_other_student_cannot_edit_someone_elses_work(self):
        work = Work.objects.create(
            author=self.student,
            title='不能被别人改',
            work_type=Work.WorkType.AI,
            description='原作者的作品。',
            status=Work.Status.REJECTED,
        )
        self.client.force_authenticate(self.other)

        response = self.client.patch(
            f'/api/works/{work.id}/',
            {
                'title': '恶意修改',
                'work_type': Work.WorkType.AI,
                'description': '不应该成功。',
            },
        )

        self.assertEqual(response.status_code, 403)
