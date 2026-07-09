import shutil
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.db import IntegrityError, transaction
from django.db.models import Count, F, Q
from django.utils import timezone
from django.utils.text import get_valid_filename
from rest_framework import parsers, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ChunkedUpload, Course, Like, Profile, Work, Vote, WorkReviewLog
from .permissions import IsAdminRole
from .serializers import (
    BulkReviewSerializer,
    CourseSerializer,
    LeaderboardSerializer,
    ProfileSerializer,
    PublicProfileSerializer,
    ReviewSerializer,
    WorkSerializer,
    WorkReviewLogSerializer,
    media_type_from_content_type,
)


MAX_WORK_UPLOAD_SIZE = 500 * 1024 * 1024
MAX_VOTES_PER_USER = 5


class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        return Response(
            {'detail': 'Registration is disabled. Please contact the administrator.'},
            status=status.HTTP_403_FORBIDDEN,
        )


class MeView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [parsers.JSONParser, parsers.FormParser, parsers.MultiPartParser]

    def get(self, request):
        return Response(ProfileSerializer(request.user.profile, context={'request': request}).data)

    def patch(self, request):
        serializer = ProfileSerializer(
            request.user.profile,
            data=request.data,
            partial=True,
            context={'request': request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class CourseViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CourseSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        queryset = Course.objects.all()
        date = self.request.query_params.get('date')
        if date:
            queryset = queryset.filter(date=date)
        return queryset


class WorkViewSet(viewsets.ModelViewSet):
    serializer_class = WorkSerializer
    parser_classes = [parsers.JSONParser, parsers.FormParser, parsers.MultiPartParser]

    def get_permissions(self):
        if self.action in ['approve', 'reject', 'pending', 'bulk_review', 'review_logs']:
            return [IsAdminRole()]
        if self.action in ['create', 'like', 'vote', 'my', 'update', 'partial_update', 'destroy']:
            return [permissions.IsAuthenticated()]
        return [permissions.AllowAny()]

    def get_queryset(self):
        queryset = WorkSerializer.setup_eager_loading(Work.objects.all())
        if self.action in ['list', 'retrieve', 'like', 'vote']:
            queryset = queryset.filter(status=Work.Status.APPROVED)
        if self.action == 'list':
            work_type = self.request.query_params.get('type')
            if work_type:
                queryset = queryset.filter(work_type=work_type)
        if self.action == 'my':
            queryset = queryset.filter(author=self.request.user)
        if self.action == 'pending':
            queryset = queryset.filter(status=Work.Status.PENDING)
            work_type = self.request.query_params.get('type')
            media_type = self.request.query_params.get('media_type')
            author = self.request.query_params.get('author')
            ordering = self.request.query_params.get('ordering')
            if work_type:
                queryset = queryset.filter(work_type=work_type)
            if media_type:
                queryset = queryset.filter(media_type=media_type)
            if author:
                queryset = queryset.filter(
                    Q(author__profile__name__icontains=author) | Q(author__username__icontains=author)
                )
            if ordering == 'oldest':
                queryset = queryset.order_by('created_at')
            else:
                queryset = queryset.order_by('-created_at')
        return queryset

    def perform_create(self, serializer):
        serializer.save(author=self.request.user, status=Work.Status.PENDING)

    def perform_update(self, serializer):
        work = self.get_object()
        if not self._can_edit_work(work):
            self.permission_denied(self.request, message='只能编辑自己的作品')

        serializer.save(
            status=Work.Status.PENDING,
            reject_reason='',
            reviewed_by=None,
            reviewed_at=None,
        )

    def destroy(self, request, *args, **kwargs):
        work = self.get_object()
        if not self._can_edit_work(work):
            self.permission_denied(request, message='只能删除自己的作品')
        return super().destroy(request, *args, **kwargs)

    def _can_edit_work(self, work):
        user = self.request.user
        profile = getattr(user, 'profile', None)
        return user.is_staff or getattr(profile, 'role', None) == Profile.Role.ADMIN or work.author_id == user.id

    @action(detail=False, methods=['get'])
    def my(self, request):
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def pending(self, request):
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        work = self.get_object()
        self._review_work(work, request.user, WorkReviewLog.Action.APPROVE)
        return Response(self.get_serializer(work).data)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        serializer = ReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reject_reason = serializer.validated_data.get('reject_reason', '').strip()
        if not reject_reason:
            return Response({'reject_reason': '打回时必须填写原因'}, status=status.HTTP_400_BAD_REQUEST)
        work = self.get_object()
        self._review_work(work, request.user, WorkReviewLog.Action.REJECT, reject_reason)
        return Response(self.get_serializer(work).data)

    @action(detail=False, methods=['post'], url_path='bulk-review')
    def bulk_review(self, request):
        serializer = BulkReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        action_name = serializer.validated_data['action']
        reject_reason = serializer.validated_data.get('reject_reason', '').strip()
        if action_name == WorkReviewLog.Action.REJECT and not reject_reason:
            return Response({'reject_reason': '批量打回时必须填写原因'}, status=status.HTTP_400_BAD_REQUEST)

        ids = serializer.validated_data['ids']
        works = list(Work.objects.filter(id__in=ids, status=Work.Status.PENDING))
        found_ids = {work.id for work in works}
        missing_ids = [work_id for work_id in ids if work_id not in found_ids]

        with transaction.atomic():
            for work in works:
                self._review_work(work, request.user, action_name, reject_reason)

        return Response({
            'reviewed_count': len(works),
            'missing_ids': missing_ids,
            'action': action_name,
        })

    @action(detail=False, methods=['get'], url_path='review-logs')
    def review_logs(self, request):
        queryset = WorkReviewLog.objects.select_related('work__author__profile', 'reviewer__profile', 'reviewer')
        work_id = request.query_params.get('work')
        if work_id:
            queryset = queryset.filter(work_id=work_id)
        serializer = WorkReviewLogSerializer(queryset[:50], many=True)
        return Response(serializer.data)

    def _review_work(self, work, reviewer, action_name, reject_reason=''):
        if action_name == WorkReviewLog.Action.APPROVE:
            work.status = Work.Status.APPROVED
            work.reject_reason = ''
        else:
            work.status = Work.Status.REJECTED
            work.reject_reason = reject_reason

        work.reviewed_by = reviewer
        work.reviewed_at = timezone.now()
        work.save(update_fields=['status', 'reject_reason', 'reviewed_by', 'reviewed_at', 'updated_at'])
        WorkReviewLog.objects.create(
            work=work,
            reviewer=reviewer,
            action=action_name,
            reason=reject_reason if action_name == WorkReviewLog.Action.REJECT else '',
        )

    @action(detail=True, methods=['post'])
    def like(self, request, pk=None):
        work = self.get_object()
        try:
            with transaction.atomic():
                Like.objects.create(user=request.user, work=work)
        except IntegrityError:
            return Response(
                {
                    'detail': '你已经点赞过这个作品',
                    **self._interaction_state(work, request.user),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                'detail': '点赞成功',
                **self._interaction_state(work, request.user),
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=['post'])
    def vote(self, request, pk=None):
        work = self.get_object()
        with transaction.atomic():
            request.user.__class__.objects.select_for_update().get(pk=request.user.pk)

            if Vote.objects.filter(user=request.user, work=work).exists():
                return Response(
                    {
                        'detail': '你已经给这个作品投过票',
                        **self._interaction_state(work, request.user),
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            used_votes = Vote.objects.filter(user=request.user).count()
            if used_votes >= MAX_VOTES_PER_USER:
                return Response(
                    {
                        'detail': '每位学员最多只能投 5 票',
                        **self._interaction_state(work, request.user),
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                with transaction.atomic():
                    Vote.objects.create(user=request.user, work=work)
            except IntegrityError:
                return Response(
                    {
                        'detail': '你已经给这个作品投过票',
                        **self._interaction_state(work, request.user),
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        remaining_votes = max(MAX_VOTES_PER_USER - Vote.objects.filter(user=request.user).count(), 0)
        return Response(
            {
                'detail': f'投票成功，还剩 {remaining_votes} 票',
                **self._interaction_state(work, request.user),
            },
            status=status.HTTP_201_CREATED,
        )

    def _interaction_state(self, work, user):
        refreshed_work = self.get_serializer(
            WorkSerializer.setup_eager_loading(Work.objects.filter(pk=work.pk)).get()
        ).data
        used_votes = Vote.objects.filter(user=user).count()
        return {
            'work': refreshed_work,
            'liked': Like.objects.filter(user=user, work=work).exists(),
            'voted': Vote.objects.filter(user=user, work=work).exists(),
            'used_votes': used_votes,
            'remaining_votes': max(MAX_VOTES_PER_USER - used_votes, 0),
            'max_votes': MAX_VOTES_PER_USER,
        }


class LeaderboardView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        queryset = (
            Work.objects.filter(status=Work.Status.APPROVED)
            .select_related('author__profile')
            .annotate(like_count=Count('likes', distinct=True), vote_count=Count('votes', distinct=True))
            .annotate(score=F('like_count') + F('vote_count'))
            .order_by('-score', '-vote_count', '-like_count')[:5]
        )
        return Response(LeaderboardSerializer(queryset, many=True).data)


class SearchView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        keyword = request.query_params.get('q', '').strip()
        if not keyword:
            return Response({'works': [], 'profiles': []})

        works = (
            WorkSerializer.setup_eager_loading(Work.objects.filter(status=Work.Status.APPROVED))
            .filter(
                Q(title__icontains=keyword)
                | Q(description__icontains=keyword)
                | Q(author__profile__name__icontains=keyword)
            )
            .distinct()[:12]
        )
        profiles = (
            Profile.objects.select_related('user')
            .filter(
                Q(name__icontains=keyword)
                | Q(school__icontains=keyword)
                | Q(mbti__icontains=keyword)
                | Q(zodiac__icontains=keyword)
                | Q(user__username__icontains=keyword)
            )
            .exclude(user__is_staff=True)
            .distinct()[:12]
        )

        return Response({
            'works': WorkSerializer(works, many=True, context={'request': request}).data,
            'profiles': PublicProfileSerializer(profiles, many=True, context={'request': request}).data,
        })


class UploadInitView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        file_name = str(request.data.get('file_name', '')).strip()
        content_type = str(request.data.get('content_type', '')).strip()
        total_size = self.to_int(request.data.get('total_size'))
        total_chunks = self.to_int(request.data.get('total_chunks'))
        media_type = media_type_from_content_type(content_type)

        if not file_name:
            return Response({'file_name': '文件名不能为空'}, status=status.HTTP_400_BAD_REQUEST)
        if not media_type:
            return Response({'content_type': '仅支持图片、PDF、MP4、WebM 和 MOV 视频'}, status=status.HTTP_400_BAD_REQUEST)
        if not total_size or total_size <= 0 or total_size > settings.WORK_MAX_UPLOAD_SIZE:
            return Response({'total_size': '文件大小必须大于 0 且不能超过 500MB'}, status=status.HTTP_400_BAD_REQUEST)
        if not total_chunks or total_chunks <= 0:
            return Response({'total_chunks': '分片数量不正确'}, status=status.HTTP_400_BAD_REQUEST)

        upload = ChunkedUpload.objects.create(
            owner=request.user,
            file_name=get_valid_filename(file_name),
            content_type=content_type,
            media_type=media_type,
            total_size=total_size,
            total_chunks=total_chunks,
        )

        return Response({
            'upload_id': str(upload.upload_id),
            'file_name': upload.file_name,
            'media_type': upload.media_type,
            'total_size': upload.total_size,
            'total_chunks': upload.total_chunks,
            'max_size': settings.WORK_MAX_UPLOAD_SIZE,
        }, status=status.HTTP_201_CREATED)

    @staticmethod
    def to_int(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None


class UploadChunkView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [parsers.MultiPartParser, parsers.FormParser]

    def post(self, request, upload_id):
        upload = self.get_upload(request, upload_id)
        if isinstance(upload, Response):
            return upload

        index = UploadInitView.to_int(request.data.get('index'))
        chunk = request.FILES.get('chunk')
        if index is None or index < 0 or index >= upload.total_chunks:
            return Response({'index': '分片序号不正确'}, status=status.HTTP_400_BAD_REQUEST)
        if not chunk:
            return Response({'chunk': '缺少分片文件'}, status=status.HTTP_400_BAD_REQUEST)

        chunk_dir = self.chunk_dir(upload.upload_id)
        chunk_dir.mkdir(parents=True, exist_ok=True)
        chunk_path = chunk_dir / f'{index}.part'
        with chunk_path.open('wb') as target:
            for piece in chunk.chunks():
                target.write(piece)

        uploaded_chunks = set(upload.uploaded_chunks)
        uploaded_chunks.add(index)
        upload.uploaded_chunks = sorted(uploaded_chunks)
        upload.save(update_fields=['uploaded_chunks', 'updated_at'])

        return Response({
            'upload_id': str(upload.upload_id),
            'received': len(upload.uploaded_chunks),
            'total_chunks': upload.total_chunks,
        })

    @staticmethod
    def get_upload(request, upload_id):
        upload = ChunkedUpload.objects.filter(upload_id=upload_id, owner=request.user).first()
        if not upload:
            return Response({'upload_id': '上传会话不存在'}, status=status.HTTP_404_NOT_FOUND)
        if upload.status == ChunkedUpload.Status.COMPLETED:
            return Response({'upload_id': '上传已经完成'}, status=status.HTTP_400_BAD_REQUEST)
        return upload

    @staticmethod
    def chunk_dir(upload_id):
        return Path(settings.WORK_UPLOAD_CHUNK_DIR) / str(upload_id)


class UploadCompleteView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, upload_id):
        upload = ChunkedUpload.objects.filter(upload_id=upload_id, owner=request.user).first()
        if not upload:
            return Response({'upload_id': '上传会话不存在'}, status=status.HTTP_404_NOT_FOUND)
        if upload.status == ChunkedUpload.Status.COMPLETED:
            return self.response_for_upload(upload)

        expected = set(range(upload.total_chunks))
        received = set(upload.uploaded_chunks)
        if expected != received:
            return Response({
                'detail': '分片尚未全部上传',
                'missing_chunks': sorted(expected - received),
            }, status=status.HTTP_400_BAD_REQUEST)

        chunk_dir = UploadChunkView.chunk_dir(upload.upload_id)
        combined_path = chunk_dir / 'combined.upload'
        with combined_path.open('wb') as combined:
            for index in range(upload.total_chunks):
                chunk_path = chunk_dir / f'{index}.part'
                if not chunk_path.exists():
                    return Response({'detail': f'缺少第 {index} 个分片'}, status=status.HTTP_400_BAD_REQUEST)
                with chunk_path.open('rb') as source:
                    shutil.copyfileobj(source, combined)

        if combined_path.stat().st_size != upload.total_size:
            return Response({'detail': '合并后的文件大小与声明大小不一致'}, status=status.HTTP_400_BAD_REQUEST)

        final_name = f'{upload.upload_id}_{upload.file_name}'
        with combined_path.open('rb') as file_obj:
            upload.file.save(final_name, File(file_obj), save=False)
        upload.status = ChunkedUpload.Status.COMPLETED
        upload.save(update_fields=['file', 'status', 'updated_at'])
        shutil.rmtree(chunk_dir, ignore_errors=True)
        return self.response_for_upload(upload)

    @staticmethod
    def response_for_upload(upload):
        return Response({
            'upload_id': str(upload.upload_id),
            'file': upload.file.url if upload.file else '',
            'file_name': upload.file_name,
            'content_type': upload.content_type,
            'media_type': upload.media_type,
            'total_size': upload.total_size,
        })
