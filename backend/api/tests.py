import shutil
import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .models import ChunkedUpload, Course, Like, Profile, Vote, Work, WorkImage, WorkReviewLog


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

    def test_public_registration_is_disabled(self):
        response = self.client.post('/api/auth/register/', {
            'username': 'new-student',
            'password': 'Student12345',
            'name': 'New Student',
        }, format='json')

        self.assertEqual(response.status_code, 403)
        self.assertFalse(User.objects.filter(username='new-student').exists())

    def test_login_returns_tokens_for_valid_credentials(self):
        response = self.client.post('/api/auth/token/', {
            'username': 'student',
            'password': 'Student12345',
        }, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)

    def test_login_rejects_wrong_password(self):
        response = self.client.post('/api/auth/token/', {
            'username': 'student',
            'password': 'WrongPassword123',
        }, format='json')

        self.assertEqual(response.status_code, 401)

    def test_refresh_token_returns_new_access_token(self):
        login_response = self.client.post('/api/auth/token/', {
            'username': 'student',
            'password': 'Student12345',
        }, format='json')

        response = self.client.post('/api/auth/token/refresh/', {
            'refresh': login_response.data['refresh'],
        }, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertIn('access', response.data)

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

    def test_student_can_upload_multiple_work_images(self):
        self.client.force_authenticate(self.student)

        response = self.client.post(
            '/api/works/',
            {
                'title': 'gallery work',
                'work_type': Work.WorkType.AI,
                'description': 'A work with multiple images.',
                'images': [
                    self.tiny_image('gallery-1.gif'),
                    self.tiny_image('gallery-2.gif'),
                ],
            },
            format='multipart',
        )

        self.assertEqual(response.status_code, 201)
        work = Work.objects.get(title='gallery work')
        self.assertEqual(work.media_type, Work.MediaType.IMAGE)
        self.assertEqual(work.gallery_images.count(), 2)
        self.assertEqual(len(response.data['images']), 2)

    def test_student_cannot_upload_more_than_ten_work_images(self):
        self.client.force_authenticate(self.student)

        response = self.client.post(
            '/api/works/',
            {
                'title': 'too many images',
                'work_type': Work.WorkType.AI,
                'description': 'A work with too many images.',
                'images': [self.tiny_image(f'gallery-{index}.gif') for index in range(11)],
            },
            format='multipart',
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Work.objects.filter(title='too many images').exists())

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

    def test_rejected_work_can_replace_gallery_images_on_resubmit(self):
        work = Work.objects.create(
            author=self.student,
            title='old gallery',
            work_type=Work.WorkType.AI,
            description='Old gallery description.',
            status=Work.Status.REJECTED,
            reject_reason='Needs clearer images.',
            reviewed_by=self.admin,
        )
        WorkImage.objects.create(work=work, image=self.tiny_image('old-gallery.gif'), order=0)
        self.client.force_authenticate(self.student)

        response = self.client.patch(
            f'/api/works/{work.id}/',
            {
                'title': 'new gallery',
                'work_type': Work.WorkType.AI,
                'description': 'New gallery description.',
                'images': [
                    self.tiny_image('new-gallery-1.gif'),
                    self.tiny_image('new-gallery-2.gif'),
                ],
            },
            format='multipart',
        )

        self.assertEqual(response.status_code, 200)
        work.refresh_from_db()
        self.assertEqual(work.title, 'new gallery')
        self.assertEqual(work.status, Work.Status.PENDING)
        self.assertEqual(work.gallery_images.count(), 2)
        self.assertEqual(work.gallery_images.first().order, 0)

    def test_gallery_work_keeps_images_when_metadata_changes_without_new_files(self):
        work = Work.objects.create(
            author=self.student,
            title='metadata gallery',
            work_type=Work.WorkType.AI,
            description='Gallery description.',
            link='https://example.com/gallery',
            media_type=Work.MediaType.IMAGE,
            status=Work.Status.REJECTED,
        )
        WorkImage.objects.create(work=work, image=self.tiny_image('metadata-gallery.gif'), order=0)
        self.client.force_authenticate(self.student)

        response = self.client.patch(
            f'/api/works/{work.id}/',
            {
                'title': 'metadata gallery updated',
                'work_type': Work.WorkType.AI,
                'description': 'Updated gallery description.',
                'link': 'https://example.com/gallery-updated',
            },
            format='multipart',
        )

        self.assertEqual(response.status_code, 200)
        work.refresh_from_db()
        self.assertEqual(work.media_type, Work.MediaType.IMAGE)
        self.assertEqual(work.gallery_images.count(), 1)

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

    def test_user_can_like_same_work_only_once(self):
        work = Work.objects.create(
            author=self.other,
            title='like once work',
            work_type=Work.WorkType.AI,
            description='Approved work.',
            status=Work.Status.APPROVED,
        )
        self.client.force_authenticate(self.student)

        first_response = self.client.post(f'/api/works/{work.id}/like/')
        second_response = self.client.post(f'/api/works/{work.id}/like/')

        self.assertEqual(first_response.status_code, 201)
        self.assertEqual(second_response.status_code, 400)
        self.assertEqual(Like.objects.filter(user=self.student, work=work).count(), 1)
        self.assertEqual(second_response.data['work']['like_count'], 1)

    def test_user_can_vote_same_work_only_once(self):
        work = Work.objects.create(
            author=self.other,
            title='vote once work',
            work_type=Work.WorkType.TRAINING,
            description='Approved work.',
            status=Work.Status.APPROVED,
        )
        self.client.force_authenticate(self.student)

        first_response = self.client.post(f'/api/works/{work.id}/vote/')
        second_response = self.client.post(f'/api/works/{work.id}/vote/')

        self.assertEqual(first_response.status_code, 201)
        self.assertEqual(second_response.status_code, 400)
        self.assertEqual(Vote.objects.filter(user=self.student, work=work).count(), 1)
        self.assertEqual(second_response.data['work']['vote_count'], 1)

    def test_user_has_only_five_votes_total(self):
        works = [
            Work.objects.create(
                author=self.other,
                title=f'vote limit work {index}',
                work_type=Work.WorkType.AI,
                description='Approved work.',
                status=Work.Status.APPROVED,
            )
            for index in range(6)
        ]
        self.client.force_authenticate(self.student)

        for index, work in enumerate(works[:5], start=1):
            response = self.client.post(f'/api/works/{work.id}/vote/')
            self.assertEqual(response.status_code, 201)
            self.assertEqual(response.data['remaining_votes'], 5 - index)

        blocked_response = self.client.post(f'/api/works/{works[5].id}/vote/')

        self.assertEqual(blocked_response.status_code, 400)
        self.assertEqual(Vote.objects.filter(user=self.student).count(), 5)
        self.assertEqual(blocked_response.data['remaining_votes'], 0)

    def test_client_cannot_forge_work_state_or_counts(self):
        self.client.force_authenticate(self.student)

        response = self.client.post('/api/works/', {
            'title': 'forged stats work',
            'work_type': Work.WorkType.AI,
            'description': 'The backend must ignore client-side status and counters.',
            'status': Work.Status.APPROVED,
            'like_count': 999,
            'vote_count': 999,
            'reviewed_by': self.admin.id,
        }, format='json')

        self.assertEqual(response.status_code, 201)
        work = Work.objects.get(title='forged stats work')
        self.assertEqual(work.status, Work.Status.PENDING)
        self.assertEqual(work.likes.count(), 0)
        self.assertEqual(work.votes.count(), 0)
        self.assertIsNone(work.reviewed_by)

    def test_courses_are_read_only_for_students(self):
        course = Course.objects.create(
            title='secure course',
            teacher='teacher',
            room='room',
            date='2026-07-19',
            start_time='09:00',
            end_time='10:00',
            status=Course.Status.UPCOMING,
        )
        self.client.force_authenticate(self.student)

        response = self.client.patch(
            f'/api/courses/{course.id}/',
            {'start_time': '20:00', 'status': Course.Status.DONE},
            format='json',
        )

        self.assertEqual(response.status_code, 405)
        course.refresh_from_db()
        self.assertEqual(str(course.start_time), '09:00:00')
        self.assertEqual(course.status, Course.Status.UPCOMING)

    def test_admin_bulk_review_creates_review_logs(self):
        works = [
            Work.objects.create(
                author=self.student,
                title=f'pending review {index}',
                work_type=Work.WorkType.AI,
                description='Pending work for bulk review.',
                status=Work.Status.PENDING,
            )
            for index in range(2)
        ]
        self.client.force_authenticate(self.admin)

        response = self.client.post('/api/works/bulk-review/', {
            'action': 'approve',
            'ids': [work.id for work in works],
        }, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['reviewed_count'], 2)
        self.assertEqual(Work.objects.filter(status=Work.Status.APPROVED, id__in=[work.id for work in works]).count(), 2)
        self.assertEqual(WorkReviewLog.objects.filter(action=WorkReviewLog.Action.APPROVE).count(), 2)

    def test_admin_can_filter_pending_works_by_author(self):
        Work.objects.create(
            author=self.student,
            title='student pending',
            work_type=Work.WorkType.TRAINING,
            description='Pending work from student.',
            status=Work.Status.PENDING,
        )
        Work.objects.create(
            author=self.other,
            title='other pending',
            work_type=Work.WorkType.AI,
            description='Pending work from other.',
            status=Work.Status.PENDING,
        )
        self.student.profile.name = '目标学员'
        self.student.profile.save(update_fields=['name'])
        self.client.force_authenticate(self.admin)

        response = self.client.get('/api/works/pending/?author=目标&type=training')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['title'], 'student pending')
