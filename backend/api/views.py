import hashlib
import re
import secrets
import shutil
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.db import IntegrityError, transaction
from django.db.models import Count, F, Q, Sum
from django.utils import timezone
from django.utils.text import get_valid_filename
from rest_framework import parsers, permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .models import (
    AttendanceAttempt,
    AttendanceRecord,
    AttendanceSession,
    ChunkedUpload,
    Course,
    Like,
    Profile,
    Tag,
    TrainingCamp,
    Vote,
    Work,
    WorkReviewLog,
)
from .permissions import IsAdminRole, IsStudentRole
from .serializers import (
    BulkReviewSerializer,
    CourseSerializer,
    LeaderboardSerializer,
    PopularTagSerializer,
    ProfileSerializer,
    PublicProfileSerializer,
    ReviewSerializer,
    TrainingCampSerializer,
    WorkSerializer,
    WorkReviewLogSerializer,
    media_type_from_content_type,
    validate_file_signature,
)


MAX_ATTENDANCE_FAILED_ATTEMPTS = 5


def active_camp():
    return TrainingCamp.get_active()


def window_is_open(starts_at, ends_at):
    now = timezone.now()
    return (not starts_at or starts_at <= now) and (not ends_at or now <= ends_at)


def attendance_now():
    return timezone.localtime()


def attendance_window_label(slot):
    starts_at, ends_at = AttendanceSession.window_for_slot(slot)
    return f'{starts_at.strftime("%H:%M")}-{ends_at.strftime("%H:%M")}'


def attendance_slot_state(selected_date, slot, now):
    starts_at, ends_at = AttendanceSession.window_for_slot(slot)
    if selected_date < now.date() or (selected_date == now.date() and now.time() >= ends_at):
        return 'expired'
    if selected_date > now.date() or (selected_date == now.date() and now.time() < starts_at):
        return 'upcoming'
    return 'active'


class CurrentTrainingCampView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        camp = active_camp()
        if not camp:
            return Response({'detail': '当前没有激活的培训期'}, status=status.HTTP_404_NOT_FOUND)
        return Response(TrainingCampSerializer(camp, context={'request': request}).data)


class ThrottledTokenObtainPairView(TokenObtainPairView):
    throttle_scope = 'login'


class ThrottledTokenRefreshView(TokenRefreshView):
    throttle_scope = 'login'


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


class StudentAttendanceTodayView(APIView):
    permission_classes = [IsStudentRole]

    def get(self, request):
        now = attendance_now()
        camp = active_camp()
        if not camp:
            return Response({'detail': '当前没有激活的培训期'}, status=status.HTTP_404_NOT_FOUND)

        sessions = {
            item.time_slot: item
            for item in AttendanceSession.objects.filter(camp=camp, date=now.date())
        }
        records = {
            item.session_id: item
            for item in AttendanceRecord.objects.filter(
                student=request.user,
                session__camp=camp,
                session__date=now.date(),
            )
        }
        slot_labels = dict(AttendanceSession.TimeSlot.choices)
        current_slot = AttendanceSession.slot_for_time(now.time())
        slots = []

        for slot, _ in AttendanceSession.TimeSlot.choices:
            session = sessions.get(slot)
            record = records.get(session.id) if session else None
            state = attendance_slot_state(now.date(), slot, now)
            slots.append({
                'slot': slot,
                'label': slot_labels[slot],
                'window': attendance_window_label(slot),
                'state': 'signed' if record else state,
                'available': bool(session and state == 'active' and not record),
                'signed': bool(record),
                'signed_at': record.signed_at if record else None,
            })

        return Response({
            'date': now.date(),
            'server_time': now,
            'current_slot': current_slot,
            'slots': slots,
        })


class StudentAttendanceCheckInView(APIView):
    permission_classes = [IsStudentRole]
    throttle_scope = 'attendance'

    def post(self, request):
        code = str(request.data.get('code', '')).strip()
        if not re.fullmatch(r'\d{4}', code):
            return Response({'code': '请输入 4 位数字签到码'}, status=status.HTTP_400_BAD_REQUEST)

        now = attendance_now()
        current_slot = AttendanceSession.slot_for_time(now.time())
        if not current_slot:
            return Response({'detail': '当前不在签到时间内，逾期不能补签'}, status=status.HTTP_400_BAD_REQUEST)

        camp = active_camp()
        if not camp:
            return Response({'detail': '当前没有激活的培训期'}, status=status.HTTP_404_NOT_FOUND)

        session = AttendanceSession.objects.filter(
            camp=camp,
            date=now.date(),
            time_slot=current_slot,
        ).first()
        if not session:
            return Response({'detail': '本时段签到码尚未生成'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            request.user.__class__.objects.select_for_update().get(pk=request.user.pk)
            if AttendanceRecord.objects.filter(session=session, student=request.user).exists():
                return Response({'detail': '本时段已经签到，请勿重复提交'}, status=status.HTTP_409_CONFLICT)

            attempt, _ = AttendanceAttempt.objects.select_for_update().get_or_create(
                session=session,
                student=request.user,
            )
            if attempt.failed_attempts >= MAX_ATTENDANCE_FAILED_ATTEMPTS:
                return Response(
                    {'detail': '签到码输错次数过多，本时段已锁定'},
                    status=status.HTTP_429_TOO_MANY_REQUESTS,
                )

            if not secrets.compare_digest(session.code, code):
                attempt.failed_attempts += 1
                remaining_attempts = MAX_ATTENDANCE_FAILED_ATTEMPTS - attempt.failed_attempts
                if remaining_attempts <= 0:
                    attempt.locked_at = now
                attempt.save(update_fields=['failed_attempts', 'locked_at', 'updated_at'])
                if remaining_attempts <= 0:
                    return Response(
                        {'detail': '签到码输错次数过多，本时段已锁定'},
                        status=status.HTTP_429_TOO_MANY_REQUESTS,
                    )
                return Response(
                    {'detail': f'签到码不正确，还可尝试 {remaining_attempts} 次'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                with transaction.atomic():
                    record = AttendanceRecord.objects.create(session=session, student=request.user)
            except IntegrityError:
                return Response({'detail': '本时段已经签到，请勿重复提交'}, status=status.HTTP_409_CONFLICT)
            attempt.delete()

        return Response({
            'detail': '签到成功',
            'slot': session.time_slot,
            'slot_label': session.get_time_slot_display(),
            'signed_at': record.signed_at,
        }, status=status.HTTP_201_CREATED)


class AdminAttendanceOverviewView(APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        now = attendance_now()
        selected_date = serializers.DateField().run_validation(request.query_params.get('date')) \
            if request.query_params.get('date') else now.date()
        camp = active_camp()
        if not camp:
            return Response({'detail': '当前没有激活的培训期'}, status=status.HTTP_404_NOT_FOUND)

        students = list(
            Profile.objects.filter(role=Profile.Role.STUDENT, user__is_active=True)
            .select_related('user')
            .order_by('name', 'user__username')
        )
        sessions = {
            item.time_slot: item
            for item in AttendanceSession.objects.filter(camp=camp, date=selected_date)
            .select_related('created_by__profile')
        }
        slot_labels = dict(AttendanceSession.TimeSlot.choices)
        slot_data = []

        for slot, _ in AttendanceSession.TimeSlot.choices:
            session = sessions.get(slot)
            records = list(
                AttendanceRecord.objects.filter(session=session)
                .select_related('student__profile')
                .order_by('signed_at')
            ) if session else []
            signed_ids = {record.student_id for record in records}
            slot_data.append({
                'session_id': session.id if session else None,
                'slot': slot,
                'label': slot_labels[slot],
                'window': attendance_window_label(slot),
                'state': attendance_slot_state(selected_date, slot, now),
                'generated': bool(session),
                'code': session.code if session else None,
                'created_at': session.created_at if session else None,
                'created_by': (
                    session.created_by.profile.name
                    if session and session.created_by and hasattr(session.created_by, 'profile')
                    else session.created_by.username if session and session.created_by else ''
                ),
                'signed_count': len(records),
                'absent_count': max(len(students) - len(records), 0) if session else None,
                'records': [
                    {
                        'student_id': record.student_id,
                        'username': record.student.username,
                        'name': record.student.profile.name,
                        'signed_at': record.signed_at,
                    }
                    for record in records
                ],
                'absent_students': [
                    {'student_id': profile.user_id, 'username': profile.user.username, 'name': profile.name}
                    for profile in students
                    if profile.user_id not in signed_ids
                ] if session else [],
            })

        return Response({
            'date': selected_date,
            'server_time': now,
            'current_slot': AttendanceSession.slot_for_time(now.time()) if selected_date == now.date() else None,
            'student_count': len(students),
            'slots': slot_data,
        })


class AdminAttendanceGenerateView(APIView):
    permission_classes = [IsAdminRole]
    throttle_scope = 'attendance'

    def post(self, request):
        now = attendance_now()
        current_slot = AttendanceSession.slot_for_time(now.time())
        if not current_slot:
            return Response(
                {'detail': '当前不在签到时段内，不能提前生成或逾期生成签到码'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        camp = active_camp()
        if not camp:
            return Response({'detail': '当前没有激活的培训期'}, status=status.HTTP_404_NOT_FOUND)

        existing = AttendanceSession.objects.filter(
            camp=camp,
            date=now.date(),
            time_slot=current_slot,
        ).first()
        if existing:
            return Response(
                {'detail': '本时段签到码已由其他管理员生成，请刷新后查看'},
                status=status.HTTP_409_CONFLICT,
            )

        for _ in range(20):
            code = f'{secrets.randbelow(10000):04d}'
            try:
                with transaction.atomic():
                    session = AttendanceSession.objects.create(
                        camp=camp,
                        date=now.date(),
                        time_slot=current_slot,
                        code=code,
                        created_by=request.user,
                    )
            except IntegrityError:
                existing = AttendanceSession.objects.filter(
                    camp=camp,
                    date=now.date(),
                    time_slot=current_slot,
                ).first()
                if existing:
                    return Response(
                        {'detail': '本时段签到码已由其他管理员生成，请刷新后查看'},
                        status=status.HTTP_409_CONFLICT,
                    )
                continue

            return Response({
                'detail': '签到码生成成功',
                'session_id': session.id,
                'date': session.date,
                'slot': session.time_slot,
                'slot_label': session.get_time_slot_display(),
                'window': attendance_window_label(session.time_slot),
                'code': session.code,
                'created_at': session.created_at,
            }, status=status.HTTP_201_CREATED)

        return Response({'detail': '签到码生成失败，请稍后重试'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


class CourseViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CourseSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        queryset = Course.objects.all()
        camp = active_camp()
        if camp:
            queryset = queryset.filter(camp=camp)
        else:
            queryset = queryset.none()
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
        camp = active_camp()
        if camp:
            queryset = queryset.filter(camp=camp)
        else:
            queryset = queryset.none()
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
        camp = active_camp()
        if not camp:
            raise serializers.ValidationError({'camp': '当前没有可投稿的培训期'})
        if not window_is_open(camp.submission_starts_at, camp.submission_ends_at):
            raise serializers.ValidationError({'camp': '当前培训期不在投稿时间内'})
        serializer.save(author=self.request.user, camp=camp, status=Work.Status.PENDING)

    def perform_update(self, serializer):
        work = self.get_object()
        if not self._can_edit_work(work):
            self.permission_denied(self.request, message='只能编辑自己的作品')
        if not window_is_open(work.camp.submission_starts_at, work.camp.submission_ends_at):
            raise serializers.ValidationError({'camp': '当前培训期不在投稿时间内'})

        serializer.save(
            status=Work.Status.PENDING,
            reject_reason='',
            reviewed_by=None,
            reviewed_at=None,
        )

    def destroy(self, request, *args, **kwargs):
        work = self.get_object()
        if not self._can_delete_work(work):
            self.permission_denied(request, message='只能删除自己的作品')
        return super().destroy(request, *args, **kwargs)

    def _can_delete_work(self, work):
        user = self.request.user
        profile = getattr(user, 'profile', None)
        is_admin = user.is_staff or getattr(profile, 'role', None) == Profile.Role.ADMIN
        return is_admin or work.author_id == user.id

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
        works = list(Work.objects.filter(id__in=ids, status=Work.Status.PENDING, camp=active_camp()))
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
        camp = work.camp
        if not window_is_open(camp.voting_starts_at, camp.voting_ends_at):
            return Response({'detail': '当前不在投票时间内'}, status=status.HTTP_400_BAD_REQUEST)
        vote_limit = camp.vote_limit
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

            used_votes = Vote.objects.filter(user=request.user, work__camp=camp).count()
            if used_votes >= vote_limit:
                return Response(
                    {
                        'detail': f'本期每位学员最多只能投 {vote_limit} 票',
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

        remaining_votes = max(vote_limit - Vote.objects.filter(user=request.user, work__camp=camp).count(), 0)
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
        used_votes = Vote.objects.filter(user=user, work__camp=work.camp).count()
        vote_limit = work.camp.vote_limit
        return {
            'work': refreshed_work,
            'liked': Like.objects.filter(user=user, work=work).exists(),
            'voted': Vote.objects.filter(user=user, work=work).exists(),
            'used_votes': used_votes,
            'remaining_votes': max(vote_limit - used_votes, 0),
            'max_votes': vote_limit,
        }


class LeaderboardView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        camp = active_camp()
        if not camp:
            return Response([])
        queryset = (
            Work.objects.filter(status=Work.Status.APPROVED, camp=camp)
            .select_related('author__profile')
            .annotate(like_count=Count('likes', distinct=True), vote_count=Count('votes', distinct=True))
            .annotate(score=F('like_count') + F('vote_count'))
            .order_by('-score', '-vote_count', '-like_count')[:5]
        )
        return Response(LeaderboardSerializer(queryset, many=True).data)


class PopularTagView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        camp = active_camp()
        if not camp:
            return Response([])
        queryset = (
            Tag.objects.filter(works__camp=camp, works__status=Work.Status.APPROVED)
            .annotate(work_count=Count('works', distinct=True))
            .order_by('-work_count', 'name')[:8]
        )
        return Response(PopularTagSerializer(queryset, many=True).data)


class SearchView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = 'search'

    def get(self, request):
        keyword = request.query_params.get('q', '').strip()
        if not keyword:
            return Response({'works': [], 'profiles': []})

        camp = active_camp()
        works = (
            WorkSerializer.setup_eager_loading(Work.objects.filter(status=Work.Status.APPROVED, camp=camp))
            .filter(
                Q(title__icontains=keyword)
                | Q(description__icontains=keyword)
                | Q(tags__name__icontains=keyword)
                | Q(author__profile__name__icontains=keyword)
            )
            .distinct()[:12]
        )
        profiles = (
            Profile.objects.select_related('user')
            .filter(
                Q(name__icontains=keyword)
                | Q(workplace__icontains=keyword)
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
    throttle_scope = 'upload'

    def post(self, request):
        file_name = str(request.data.get('file_name', '')).strip()
        content_type = str(request.data.get('content_type', '')).strip()
        expected_sha256 = str(request.data.get('sha256', '')).strip().lower()
        total_size = self.to_int(request.data.get('total_size'))
        total_chunks = self.to_int(request.data.get('total_chunks'))
        media_type = media_type_from_content_type(content_type)
        camp = active_camp()

        if not camp:
            return Response({'camp': '当前没有可投稿的培训期'}, status=status.HTTP_400_BAD_REQUEST)
        if not window_is_open(camp.submission_starts_at, camp.submission_ends_at):
            return Response({'camp': '当前培训期不在投稿时间内'}, status=status.HTTP_400_BAD_REQUEST)
        if not file_name:
            return Response({'file_name': '文件名不能为空'}, status=status.HTTP_400_BAD_REQUEST)
        if not media_type:
            return Response({'content_type': '仅支持图片、PDF、MP4、WebM 和 MOV 视频'}, status=status.HTTP_400_BAD_REQUEST)
        if not total_size or total_size <= 0 or total_size > settings.WORK_MAX_UPLOAD_SIZE:
            return Response({'total_size': '文件大小必须大于 0 且不能超过 500MB'}, status=status.HTTP_400_BAD_REQUEST)
        if not total_chunks or total_chunks <= 0:
            return Response({'total_chunks': '分片数量不正确'}, status=status.HTTP_400_BAD_REQUEST)
        if total_chunks > settings.WORK_MAX_UPLOAD_CHUNKS:
            return Response({'total_chunks': '分片数量超过限制'}, status=status.HTTP_400_BAD_REQUEST)
        if expected_sha256 and not re.fullmatch(r'[0-9a-f]{64}', expected_sha256):
            return Response({'sha256': 'SHA-256 摘要格式不正确'}, status=status.HTTP_400_BAD_REQUEST)

        pending_uploads = ChunkedUpload.objects.filter(
            owner=request.user,
            consumed_at__isnull=True,
            expires_at__gt=timezone.now(),
        )
        if pending_uploads.count() >= settings.WORK_MAX_ACTIVE_UPLOADS:
            return Response({'detail': '未完成的上传任务过多，请完成或等待过期后再试'}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        pending_bytes = pending_uploads.aggregate(total=Sum('total_size'))['total'] or 0
        if pending_bytes + total_size > settings.WORK_MAX_PENDING_UPLOAD_BYTES:
            return Response({'detail': '待处理上传文件总量超过个人配额'}, status=status.HTTP_429_TOO_MANY_REQUESTS)

        upload = ChunkedUpload.objects.create(
            camp=camp,
            owner=request.user,
            file_name=get_valid_filename(file_name),
            content_type=content_type,
            media_type=media_type,
            total_size=total_size,
            total_chunks=total_chunks,
            expected_sha256=expected_sha256,
            expires_at=timezone.now() + timedelta(hours=settings.WORK_UPLOAD_SESSION_TTL_HOURS),
        )

        return Response({
            'upload_id': str(upload.upload_id),
            'file_name': upload.file_name,
            'media_type': upload.media_type,
            'total_size': upload.total_size,
            'total_chunks': upload.total_chunks,
            'max_size': settings.WORK_MAX_UPLOAD_SIZE,
            'expires_at': upload.expires_at,
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
    throttle_scope = 'upload'

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
        if chunk.size <= 0 or chunk.size > settings.WORK_MAX_UPLOAD_CHUNK_SIZE:
            return Response({'chunk': '分片为空或超过单片大小限制'}, status=status.HTTP_400_BAD_REQUEST)

        chunk_dir = self.chunk_dir(upload.upload_id)
        chunk_dir.mkdir(parents=True, exist_ok=True)
        chunk_path = chunk_dir / f'{index}.part'
        existing_size = chunk_path.stat().st_size if chunk_path.exists() else 0
        received_size = sum(path.stat().st_size for path in chunk_dir.glob('*.part')) - existing_size
        if received_size + chunk.size > upload.total_size:
            return Response({'chunk': '分片总大小超过声明的文件大小'}, status=status.HTTP_400_BAD_REQUEST)
        with chunk_path.open('wb') as target:
            for piece in chunk.chunks():
                target.write(piece)

        with transaction.atomic():
            locked_upload = ChunkedUpload.objects.select_for_update().get(pk=upload.pk)
            uploaded_chunks = set(locked_upload.uploaded_chunks)
            uploaded_chunks.add(index)
            locked_upload.uploaded_chunks = sorted(uploaded_chunks)
            locked_upload.save(update_fields=['uploaded_chunks', 'updated_at'])
            upload.uploaded_chunks = locked_upload.uploaded_chunks

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
        if upload.status != ChunkedUpload.Status.UPLOADING:
            return Response({'upload_id': '上传已经完成'}, status=status.HTTP_400_BAD_REQUEST)
        if upload.expires_at <= timezone.now():
            return Response({'upload_id': '上传会话已过期，请重新上传'}, status=status.HTTP_410_GONE)
        return upload

    @staticmethod
    def chunk_dir(upload_id):
        return Path(settings.WORK_UPLOAD_CHUNK_DIR) / str(upload_id)


class UploadCompleteView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    throttle_scope = 'upload'

    def post(self, request, upload_id):
        upload = ChunkedUpload.objects.filter(upload_id=upload_id, owner=request.user).first()
        if not upload:
            return Response({'upload_id': '上传会话不存在'}, status=status.HTTP_404_NOT_FOUND)
        if upload.status != ChunkedUpload.Status.UPLOADING:
            return self.response_for_upload(upload)
        if upload.expires_at <= timezone.now():
            return Response({'upload_id': '上传会话已过期，请重新上传'}, status=status.HTTP_410_GONE)

        expected = set(range(upload.total_chunks))
        received = set(upload.uploaded_chunks)
        if expected != received:
            return Response({
                'detail': '分片尚未全部上传',
                'missing_chunks': sorted(expected - received),
            }, status=status.HTTP_400_BAD_REQUEST)

        chunk_dir = UploadChunkView.chunk_dir(upload.upload_id)
        combined_path = chunk_dir / 'combined.upload'
        digest = hashlib.sha256()
        with combined_path.open('wb') as combined:
            for index in range(upload.total_chunks):
                chunk_path = chunk_dir / f'{index}.part'
                if not chunk_path.exists():
                    return Response({'detail': f'缺少第 {index} 个分片'}, status=status.HTTP_400_BAD_REQUEST)
                with chunk_path.open('rb') as source:
                    while piece := source.read(1024 * 1024):
                        digest.update(piece)
                        combined.write(piece)

        if combined_path.stat().st_size != upload.total_size:
            combined_path.unlink(missing_ok=True)
            return Response({'detail': '合并后的文件大小与声明大小不一致'}, status=status.HTTP_400_BAD_REQUEST)

        actual_sha256 = digest.hexdigest()
        if upload.expected_sha256 and upload.expected_sha256 != actual_sha256:
            combined_path.unlink(missing_ok=True)
            return Response({'detail': '文件摘要校验失败，请重新上传'}, status=status.HTTP_400_BAD_REQUEST)
        with combined_path.open('rb') as combined_file:
            valid_signature = validate_file_signature(combined_file, upload.content_type)
        if not valid_signature:
            combined_path.unlink(missing_ok=True)
            return Response({'detail': '文件内容与声明类型不匹配或文件已损坏'}, status=status.HTTP_400_BAD_REQUEST)

        final_name = f'{upload.upload_id}_{upload.file_name}'
        with combined_path.open('rb') as file_obj:
            upload.file.save(final_name, File(file_obj), save=False)
        upload.status = ChunkedUpload.Status.COMPLETED
        upload.sha256 = actual_sha256
        upload.save(update_fields=['file', 'sha256', 'status', 'updated_at'])
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
            'sha256': upload.sha256,
            'expires_at': upload.expires_at,
        })
