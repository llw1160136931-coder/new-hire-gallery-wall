import hashlib
import shutil
import tempfile
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from .models import ChunkedUpload, Course, Like, Profile, Tag, TrainingCamp, Vote, Work, WorkImage, WorkReviewLog


TEST_MEDIA_ROOT = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class WorkApiTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.camp = TrainingCamp.get_active()
        self.camp.name = 'Test camp'
        self.camp.start_date = '2026-07-19'
        self.camp.end_date = '2026-07-24'
        self.camp.vote_limit = 5
        self.camp.save()
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

    def test_me_returns_role_from_authenticated_account(self):
        self.client.force_authenticate(self.student)
        student_response = self.client.get('/api/me/')

        self.client.force_authenticate(self.admin)
        admin_response = self.client.get('/api/me/')

        self.assertEqual(student_response.status_code, 200)
        self.assertEqual(student_response.data['role'], Profile.Role.STUDENT)
        self.assertEqual(admin_response.status_code, 200)
        self.assertEqual(admin_response.data['role'], Profile.Role.ADMIN)

    def test_student_cannot_access_admin_review_queue(self):
        self.client.force_authenticate(self.student)

        response = self.client.get('/api/works/pending/')

        self.assertEqual(response.status_code, 403)

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
        self.assertEqual(upload.sha256, hashlib.sha256(content).hexdigest())

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
        upload.refresh_from_db()
        self.assertEqual(upload.status, ChunkedUpload.Status.CONSUMED)
        self.assertIsNotNone(upload.consumed_at)

        reused_response = self.client.post('/api/works/', {
            'title': '重复使用上传文件',
            'work_type': Work.WorkType.TRAINING,
            'description': '同一个上传结果不能重复使用。',
            'upload_id': upload_id,
        }, format='multipart')
        self.assertEqual(reused_response.status_code, 400)

    def test_upload_init_rejects_file_larger_than_500mb(self):
        self.client.force_authenticate(self.student)

        response = self.client.post('/api/uploads/init/', {
            'file_name': 'too-big.mp4',
            'content_type': 'video/mp4',
            'total_size': 500 * 1024 * 1024 + 1,
            'total_chunks': 101,
        }, format='json')

        self.assertEqual(response.status_code, 400)

    def test_chunked_upload_rejects_invalid_file_signature(self):
        self.client.force_authenticate(self.student)
        content = b'not actually a pdf file'
        init_response = self.client.post('/api/uploads/init/', {
            'file_name': 'fake.pdf',
            'content_type': 'application/pdf',
            'total_size': len(content),
            'total_chunks': 1,
        }, format='json')
        upload_id = init_response.data['upload_id']
        chunk = SimpleUploadedFile('fake.part0', content, content_type='application/octet-stream')
        self.client.post(f'/api/uploads/{upload_id}/chunk/', {'index': 0, 'chunk': chunk}, format='multipart')

        response = self.client.post(f'/api/uploads/{upload_id}/complete/')

        self.assertEqual(response.status_code, 400)
        self.assertEqual(ChunkedUpload.objects.get(upload_id=upload_id).status, ChunkedUpload.Status.UPLOADING)

    def test_expired_upload_session_cannot_receive_chunks(self):
        self.client.force_authenticate(self.student)
        init_response = self.client.post('/api/uploads/init/', {
            'file_name': 'expired.pdf',
            'content_type': 'application/pdf',
            'total_size': 8,
            'total_chunks': 1,
        }, format='json')
        upload = ChunkedUpload.objects.get(upload_id=init_response.data['upload_id'])
        upload.expires_at = timezone.now() - timedelta(seconds=1)
        upload.save(update_fields=['expires_at'])

        response = self.client.post(
            f'/api/uploads/{upload.upload_id}/chunk/',
            {'index': 0, 'chunk': SimpleUploadedFile('expired.part0', b'%PDF-1.4')},
            format='multipart',
        )

        self.assertEqual(response.status_code, 410)

    def test_current_camp_endpoint_and_lists_are_isolated(self):
        old_camp = TrainingCamp.objects.create(
            name='Old camp',
            slug='old-camp',
            start_date='2025-07-01',
            end_date='2025-07-05',
        )
        Work.objects.create(
            camp=old_camp,
            author=self.student,
            title='Old approved work',
            work_type=Work.WorkType.AI,
            description='Should stay in history.',
            status=Work.Status.APPROVED,
        )
        current_work = Work.objects.create(
            camp=self.camp,
            author=self.student,
            title='Current approved work',
            work_type=Work.WorkType.AI,
            description='Should be visible now.',
            status=Work.Status.APPROVED,
        )
        Course.objects.create(
            camp=self.camp,
            title='Current course',
            teacher='teacher',
            room='room',
            date='2026-07-20',
            start_time='09:00',
            end_time='10:00',
        )

        camp_response = self.client.get('/api/camps/current/')
        works_response = self.client.get('/api/works/')

        self.assertEqual(camp_response.status_code, 200)
        self.assertEqual(camp_response.data['id'], self.camp.id)
        self.assertIn('2026-07-20', [str(value) for value in camp_response.data['training_dates']])
        self.assertEqual([item['id'] for item in works_response.data], [current_work.id])

    def test_student_can_submit_ai_competition_work(self):
        self.client.force_authenticate(self.student)

        response = self.client.post('/api/works/', {
            'title': 'AI 比赛参赛作品',
            'work_type': Work.WorkType.AI_COMPETITION,
            'description': '学员在投稿时主动选择 AI 比赛作品分类。',
        }, format='json')

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['work_type'], Work.WorkType.AI_COMPETITION)
        self.assertEqual(response.data['work_type_label'], 'AI 比赛作品')
        self.assertEqual(response.data['status'], Work.Status.PENDING)
        self.assertTrue(Work.objects.filter(
            author=self.student,
            work_type=Work.WorkType.AI_COMPETITION,
        ).exists())

    def test_public_ai_competition_filter_only_returns_current_approved_competition_works(self):
        competition_work = Work.objects.create(
            camp=self.camp,
            author=self.student,
            title='当前比赛作品',
            work_type=Work.WorkType.AI_COMPETITION,
            description='应该出现在比赛分类中。',
            status=Work.Status.APPROVED,
        )
        Work.objects.create(
            camp=self.camp,
            author=self.other,
            title='普通 AI 作品',
            work_type=Work.WorkType.AI,
            description='不应该出现在比赛分类中。',
            status=Work.Status.APPROVED,
        )
        Work.objects.create(
            camp=self.camp,
            author=self.other,
            title='待审比赛作品',
            work_type=Work.WorkType.AI_COMPETITION,
            description='待审核作品不应该公开。',
            status=Work.Status.PENDING,
        )
        old_camp = TrainingCamp.objects.create(
            name='Old competition camp',
            slug='old-competition-camp',
            start_date='2025-07-01',
            end_date='2025-07-05',
        )
        Work.objects.create(
            camp=old_camp,
            author=self.student,
            title='历史比赛作品',
            work_type=Work.WorkType.AI_COMPETITION,
            description='历史培训期作品不应该进入当前列表。',
            status=Work.Status.APPROVED,
        )

        response = self.client.get('/api/works/?type=ai_competition')
        leaderboard_response = self.client.get('/api/leaderboard/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual([item['id'] for item in response.data], [competition_work.id])
        leaderboard_item = next(item for item in leaderboard_response.data if item['id'] == competition_work.id)
        self.assertEqual(leaderboard_item['work_type_label'], 'AI 比赛作品')

    def test_leaderboard_excludes_display_only_work(self):
        display_only_work = Work.objects.create(
            camp=self.camp,
            author=self.student,
            title='官方培训直播',
            work_type=Work.WorkType.TRAINING,
            description='用于作品墙展示，但不参与学员作品排行。',
            status=Work.Status.APPROVED,
            include_in_leaderboard=False,
        )
        ranked_work = Work.objects.create(
            camp=self.camp,
            author=self.other,
            title='学员参赛作品',
            work_type=Work.WorkType.TRAINING,
            description='应该进入排行榜的学员作品。',
            status=Work.Status.APPROVED,
        )
        Like.objects.create(user=self.student, work=display_only_work)
        Like.objects.create(user=self.other, work=display_only_work)
        Vote.objects.create(user=self.student, work=display_only_work)
        Vote.objects.create(user=self.other, work=display_only_work)

        works_response = self.client.get('/api/works/')
        leaderboard_response = self.client.get('/api/leaderboard/')

        self.assertEqual(works_response.status_code, 200)
        self.assertIn(display_only_work.id, [item['id'] for item in works_response.data])
        self.assertEqual(leaderboard_response.status_code, 200)
        self.assertNotIn(display_only_work.id, [item['id'] for item in leaderboard_response.data])
        self.assertIn(ranked_work.id, [item['id'] for item in leaderboard_response.data])

    def test_vote_limit_resets_for_each_training_camp(self):
        self.camp.vote_limit = 1
        self.camp.save(update_fields=['vote_limit'])
        old_camp = TrainingCamp.objects.create(
            name='Old voting camp',
            slug='old-voting-camp',
            start_date='2025-07-01',
            end_date='2025-07-05',
            vote_limit=1,
        )
        old_work = Work.objects.create(
            camp=old_camp,
            author=self.other,
            title='Old voted work',
            work_type=Work.WorkType.AI,
            description='Historical vote.',
            status=Work.Status.APPROVED,
        )
        current_works = [
            Work.objects.create(
                camp=self.camp,
                author=self.other,
                title=f'Current vote work {index}',
                work_type=Work.WorkType.AI,
                description='Current camp vote.',
                status=Work.Status.APPROVED,
            )
            for index in range(2)
        ]
        Vote.objects.create(user=self.student, work=old_work)
        self.client.force_authenticate(self.student)

        first_response = self.client.post(f'/api/works/{current_works[0].id}/vote/')
        second_response = self.client.post(f'/api/works/{current_works[1].id}/vote/')

        self.assertEqual(first_response.status_code, 201)
        self.assertEqual(second_response.status_code, 400)
        self.assertEqual(second_response.data['remaining_votes'], 0)

    def test_search_returns_backend_work_and_profile_results(self):
        self.client.force_authenticate(self.student)
        self.student.profile.name = '林小夏'
        self.student.profile.workplace = '示例科技公司'
        self.student.profile.save(update_fields=['name', 'workplace'])
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

    def test_student_can_update_workplace_mbti_and_zodiac_from_allowed_values(self):
        self.client.force_authenticate(self.student)

        response = self.client.patch('/api/me/', {
            'workplace': '示例科技公司',
            'mbti': Profile.Mbti.ENFP,
            'zodiac': Profile.Zodiac.LIBRA,
        }, format='json')

        self.assertEqual(response.status_code, 200)
        self.student.profile.refresh_from_db()
        self.assertEqual(self.student.profile.workplace, '示例科技公司')
        self.assertEqual(self.student.profile.mbti, Profile.Mbti.ENFP)
        self.assertEqual(self.student.profile.zodiac, Profile.Zodiac.LIBRA)

    def test_profile_rejects_unknown_mbti_and_zodiac_values(self):
        self.client.force_authenticate(self.student)

        response = self.client.patch('/api/me/', {
            'mbti': 'ABCD',
            'zodiac': '不存在的星座',
        }, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertIn('mbti', response.data)
        self.assertIn('zodiac', response.data)

    def test_student_can_publish_normalized_real_tags(self):
        self.client.force_authenticate(self.student)

        response = self.client.post('/api/works/', {
            'title': 'Tagged work',
            'work_type': Work.WorkType.AI,
            'description': 'A work with real persisted tags.',
            'tags': '["AI 海报", "#ai 海报", "流程 Demo"]',
        }, format='multipart')

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['tags'], ['AI 海报', '流程 Demo'])
        work = Work.objects.get(title='Tagged work')
        self.assertEqual(list(work.tags.values_list('name', flat=True)), ['AI 海报', '流程 Demo'])
        self.assertEqual(Tag.objects.count(), 2)

    def test_popular_tags_use_only_current_approved_works(self):
        popular = Tag.objects.create(name='热门实践')
        pending_only = Tag.objects.create(name='待审标签')
        old_only = Tag.objects.create(name='历史标签')
        approved_works = [
            Work.objects.create(
                camp=self.camp,
                author=self.student,
                title=f'approved tagged {index}',
                work_type=Work.WorkType.AI,
                description='Approved tagged work.',
                status=Work.Status.APPROVED,
            )
            for index in range(2)
        ]
        for work in approved_works:
            work.tags.add(popular)
        pending_work = Work.objects.create(
            camp=self.camp,
            author=self.student,
            title='pending tagged',
            work_type=Work.WorkType.AI,
            description='Pending tagged work.',
            status=Work.Status.PENDING,
        )
        pending_work.tags.add(pending_only)
        old_camp = TrainingCamp.objects.create(
            name='Tag history',
            slug='tag-history',
            start_date='2025-01-01',
            end_date='2025-01-02',
        )
        old_work = Work.objects.create(
            camp=old_camp,
            author=self.student,
            title='old tagged',
            work_type=Work.WorkType.AI,
            description='Old tagged work.',
            status=Work.Status.APPROVED,
        )
        old_work.tags.add(old_only)

        response = self.client.get('/api/tags/popular/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [{'id': popular.id, 'name': '热门实践', 'work_count': 2}])

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

    def test_student_can_delete_own_work(self):
        work = Work.objects.create(
            camp=self.camp,
            author=self.student,
            title='自己的作品',
            work_type=Work.WorkType.TRAINING,
            description='学生应该可以删除自己的作品。',
            status=Work.Status.APPROVED,
        )
        self.client.force_authenticate(self.student)

        response = self.client.delete(f'/api/works/{work.id}/')

        self.assertEqual(response.status_code, 204)
        self.assertFalse(Work.objects.filter(id=work.id).exists())

    def test_student_cannot_delete_another_students_work(self):
        work = Work.objects.create(
            camp=self.camp,
            author=self.student,
            title='其他学员的作品',
            work_type=Work.WorkType.AI,
            description='不能被其他学员删除。',
            status=Work.Status.APPROVED,
        )
        self.client.force_authenticate(self.other)

        response = self.client.delete(f'/api/works/{work.id}/')

        self.assertEqual(response.status_code, 403)
        self.assertTrue(Work.objects.filter(id=work.id).exists())

    def test_admin_can_delete_students_work(self):
        work = Work.objects.create(
            camp=self.camp,
            author=self.student,
            title='管理员可删除的作品',
            work_type=Work.WorkType.TRAINING,
            description='管理员应该可以删除学员作品。',
            status=Work.Status.PENDING,
        )
        self.client.force_authenticate(self.admin)

        response = self.client.delete(f'/api/works/{work.id}/')

        self.assertEqual(response.status_code, 204)
        self.assertFalse(Work.objects.filter(id=work.id).exists())

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
            'include_in_leaderboard': False,
        }, format='json')

        self.assertEqual(response.status_code, 201)
        work = Work.objects.get(title='forged stats work')
        self.assertEqual(work.status, Work.Status.PENDING)
        self.assertEqual(work.likes.count(), 0)
        self.assertEqual(work.votes.count(), 0)
        self.assertIsNone(work.reviewed_by)
        self.assertTrue(work.include_in_leaderboard)

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

    def test_admin_can_reclassify_published_work_without_resetting_review(self):
        reviewed_at = timezone.now() - timedelta(hours=1)
        work = Work.objects.create(
            camp=self.camp,
            author=self.student,
            title='已发布普通 AI 作品',
            work_type=Work.WorkType.AI,
            description='管理员可以将它归入 AI 比赛作品。',
            status=Work.Status.APPROVED,
            include_in_leaderboard=False,
            reviewed_by=self.admin,
            reviewed_at=reviewed_at,
        )
        self.camp.submission_ends_at = timezone.now() - timedelta(minutes=1)
        self.camp.save(update_fields=['submission_ends_at'])
        self.client.force_authenticate(self.admin)

        response = self.client.patch(
            f'/api/works/{work.id}/classification/',
            {'work_type': Work.WorkType.AI_COMPETITION, 'title': '不应被修改'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        work.refresh_from_db()
        self.assertEqual(work.work_type, Work.WorkType.AI_COMPETITION)
        self.assertEqual(work.title, '已发布普通 AI 作品')
        self.assertEqual(work.status, Work.Status.APPROVED)
        self.assertFalse(work.include_in_leaderboard)
        self.assertEqual(work.reviewed_by, self.admin)
        self.assertEqual(work.reviewed_at, reviewed_at)

    def test_student_cannot_use_admin_work_classification_endpoint(self):
        work = Work.objects.create(
            camp=self.camp,
            author=self.student,
            title='不能自行绕过审核改分类',
            work_type=Work.WorkType.AI,
            description='普通学员不能调用管理员分类接口。',
            status=Work.Status.APPROVED,
        )
        self.client.force_authenticate(self.student)

        response = self.client.patch(
            f'/api/works/{work.id}/classification/',
            {'work_type': 'ai_competition'},
            format='json',
        )

        self.assertEqual(response.status_code, 403)
        work.refresh_from_db()
        self.assertEqual(work.work_type, Work.WorkType.AI)

    def test_admin_classification_rejects_invalid_work_type(self):
        work = Work.objects.create(
            camp=self.camp,
            author=self.student,
            title='分类校验作品',
            work_type=Work.WorkType.TRAINING,
            description='非法分类不能写入数据库。',
            status=Work.Status.APPROVED,
        )
        self.client.force_authenticate(self.admin)

        response = self.client.patch(
            f'/api/works/{work.id}/classification/',
            {'work_type': 'not-a-real-type'},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        work.refresh_from_db()
        self.assertEqual(work.work_type, Work.WorkType.TRAINING)

    def test_admin_cannot_reclassify_historical_camp_work(self):
        old_camp = TrainingCamp.objects.create(
            name='Historical classification camp',
            slug='historical-classification-camp',
            start_date='2025-06-01',
            end_date='2025-06-05',
        )
        work = Work.objects.create(
            camp=old_camp,
            author=self.student,
            title='历史培训期作品',
            work_type=Work.WorkType.AI,
            description='管理员分类接口不能跨培训期修改历史数据。',
            status=Work.Status.APPROVED,
        )
        self.client.force_authenticate(self.admin)

        response = self.client.patch(
            f'/api/works/{work.id}/classification/',
            {'work_type': Work.WorkType.AI_COMPETITION},
            format='json',
        )

        self.assertEqual(response.status_code, 404)
        work.refresh_from_db()
        self.assertEqual(work.work_type, Work.WorkType.AI)

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
