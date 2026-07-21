import hashlib
import re
import secrets
import shutil
from collections.abc import Mapping
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.files import File
from django.db import IntegrityError, transaction
from django.db.models import Count, F, Q, Sum
from django.http import FileResponse, Http404, HttpResponse
from django.utils import timezone
from django.utils.http import content_disposition_header
from django.utils.text import get_valid_filename
from rest_framework import mixins, parsers, permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .attendance_services import (
    AttendanceServiceError,
    grant_makeup,
    is_camp_member,
    revoke_makeup,
)
from .models import (
    AttendanceAttempt,
    AttendanceRecord,
    AttendanceSession,
    ChunkedUpload,
    Course,
    CourseResource,
    Like,
    Profile,
    Tag,
    TrainingCamp,
    TrainingCampMembership,
    Vote,
    Work,
    WorkReviewLog,
)
from .course_files import (
    course_mind_map_content_type,
    course_resource_content_type,
    validate_course_mind_map_file,
    validate_course_resource_file,
)
from .permissions import IsAdminRole, IsAttendanceAdminRole, IsStudentRole
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
from .work_files import is_html_filename


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


def safe_original_filename(filename):
    leaf_name = re.split(r'[/\\]+', filename or '')[-1]
    return (get_valid_filename(leaf_name) or 'course-file')[:255]


def protected_course_file_response(field_file, original_filename, content_type, file_size, *, attachment):
    if not field_file or not field_file.name:
        raise Http404('文件不存在')

    try:
        exists = field_file.storage.exists(field_file.name)
    except (OSError, ValueError):
        exists = False
    if not exists:
        raise Http404('文件不存在')

    if settings.COURSE_MATERIAL_USE_X_ACCEL:
        prefix = settings.COURSE_MATERIAL_X_ACCEL_PREFIX.rstrip('/') + '/'
        internal_path = prefix + quote(field_file.name.replace('\\', '/'), safe='/')
        response = HttpResponse()
        response['X-Accel-Redirect'] = internal_path
        response['Content-Type'] = content_type or 'application/octet-stream'
        response['Content-Disposition'] = content_disposition_header(attachment, original_filename)
        if file_size:
            response['Content-Length'] = file_size
    else:
        response = FileResponse(
            field_file.open('rb'),
            as_attachment=attachment,
            filename=original_filename,
            content_type=content_type or 'application/octet-stream',
        )

    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    if attachment and (content_type or 'application/octet-stream') == 'application/octet-stream':
        response['Content-Security-Policy'] = "sandbox; default-src 'none'"
    return response


class CurrentTrainingCampView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        camp = active_camp()
        if not camp:
            return Response({'detail': '当前没有激活的培训期'}, status=status.HTTP_404_NOT_FOUND)
        return Response(TrainingCampSerializer(camp, context={'request': request}).data)


class LoadTestIdentityView(APIView):
    """Public, read-only proof that this backend is the intended load-test target."""

    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    throttle_classes = []

    def get(self, request):
        camp = active_camp()
        loadtest_mode = settings.LOADTEST_MODE
        response = Response({
            'schema_version': 1,
            'loadtest_mode': loadtest_mode,
            'target_id': settings.LOADTEST_TARGET_ID if loadtest_mode else None,
            'active_camp_slug': camp.slug if camp else None,
        })
        response['Cache-Control'] = 'no-store, max-age=0'
        response['Pragma'] = 'no-cache'
        return response


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
        if not is_camp_member(request.user, camp):
            return Response({'detail': '当前账号不属于本培训期'}, status=status.HTTP_403_FORBIDDEN)

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
                status=AttendanceRecord.Status.ACTIVE,
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
                'source_label': record.get_source_display() if record else None,
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
        if not is_camp_member(request.user, camp):
            return Response({'detail': '当前账号不属于本培训期'}, status=status.HTTP_403_FORBIDDEN)

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
    permission_classes = [IsAttendanceAdminRole]

    def get(self, request):
        now = attendance_now()
        selected_date = serializers.DateField().run_validation(request.query_params.get('date')) \
            if request.query_params.get('date') else now.date()
        camp = active_camp()
        if not camp:
            return Response({'detail': '当前没有激活的培训期'}, status=status.HTTP_404_NOT_FOUND)

        memberships = list(
            TrainingCampMembership.objects.filter(
                camp=camp,
                student__is_active=True,
                student__is_staff=False,
                student__is_superuser=False,
                student__profile__role=Profile.Role.STUDENT,
            )
            .select_related('student__profile')
            .order_by('student__profile__name', 'student__username')
        )
        students = [membership.student for membership in memberships]
        student_ids = {student.id for student in students}
        sessions = {
            item.time_slot: item
            for item in AttendanceSession.objects.filter(camp=camp, date=selected_date)
            .select_related('created_by__profile')
        }
        slot_labels = dict(AttendanceSession.TimeSlot.choices)
        slot_data = []

        for slot, _ in AttendanceSession.TimeSlot.choices:
            session = sessions.get(slot)
            slot_state = attendance_slot_state(selected_date, slot, now)
            records = list(
                AttendanceRecord.objects.filter(
                    session=session,
                    student_id__in=student_ids,
                    status=AttendanceRecord.Status.ACTIVE,
                )
                .select_related('student__profile', 'recorded_by__profile')
                .order_by('signed_at')
            ) if session else []
            signed_ids = {record.student_id for record in records}
            slot_data.append({
                'session_id': session.id if session else None,
                'slot': slot,
                'label': slot_labels[slot],
                'window': attendance_window_label(slot),
                'state': slot_state,
                'generated': bool(session),
                'can_makeup': bool(session and slot_state == 'expired'),
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
                        'record_id': record.id,
                        'student_id': record.student_id,
                        'username': record.student.username,
                        'name': record.student.profile.name,
                        'signed_at': record.signed_at,
                        'source': record.source,
                        'source_label': record.get_source_display(),
                        'recorded_by': (
                            {
                                'username': record.recorded_by.username,
                                'name': (
                                    record.recorded_by.profile.name
                                    if hasattr(record.recorded_by, 'profile')
                                    else ''
                                ),
                            }
                            if record.source == AttendanceRecord.Source.ADMIN_MAKEUP
                            and record.recorded_by
                            else None
                        ),
                        'makeup_reason': (
                            record.makeup_reason
                            if record.source == AttendanceRecord.Source.ADMIN_MAKEUP
                            else ''
                        ),
                        'can_revoke': (
                            record.source == AttendanceRecord.Source.ADMIN_MAKEUP
                            and record.status == AttendanceRecord.Status.ACTIVE
                        ),
                    }
                    for record in records
                ],
                'absent_students': [
                    {'student_id': student.id, 'username': student.username, 'name': student.profile.name}
                    for student in students
                    if student.id not in signed_ids
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
    permission_classes = [IsAttendanceAdminRole]
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


class StrictAttendanceInputSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if isinstance(data, Mapping):
            unknown_fields = set(data.keys()) - set(self.fields)
            if unknown_fields:
                field_names = ', '.join(sorted(unknown_fields))
                raise serializers.ValidationError({
                    'detail': f'包含不允许的字段：{field_names}',
                })
        return super().to_internal_value(data)


class AttendanceMakeupInputSerializer(StrictAttendanceInputSerializer):
    session_id = serializers.IntegerField(min_value=1)
    student_id = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(min_length=5, max_length=200, trim_whitespace=True)


class AttendanceRevokeInputSerializer(StrictAttendanceInputSerializer):
    reason = serializers.CharField(min_length=5, max_length=200, trim_whitespace=True)


class AdminAttendanceMakeupView(APIView):
    permission_classes = [IsAttendanceAdminRole]
    throttle_scope = 'attendance_admin'

    def post(self, request):
        serializer = AttendanceMakeupInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            record, reactivated = grant_makeup(
                actor=request.user,
                now=attendance_now(),
                **serializer.validated_data,
            )
        except AttendanceServiceError as exc:
            return Response({'detail': exc.detail}, status=exc.status_code)

        return Response({
            'detail': '补签成功',
            'record_id': record.id,
            'student_id': record.student_id,
            'signed_at': record.signed_at,
            'source': record.source,
            'source_label': record.get_source_display(),
            'reactivated': reactivated,
        }, status=status.HTTP_201_CREATED)


class AdminAttendanceMakeupRevokeView(APIView):
    permission_classes = [IsAttendanceAdminRole]
    throttle_scope = 'attendance_admin'

    def post(self, request, record_id):
        serializer = AttendanceRevokeInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            record = revoke_makeup(
                record_id=record_id,
                actor=request.user,
                now=attendance_now(),
                **serializer.validated_data,
            )
        except AttendanceServiceError as exc:
            return Response({'detail': exc.detail}, status=exc.status_code)

        return Response({
            'detail': '补签已撤销',
            'record_id': record.id,
            'status': record.status,
            'revoked_at': record.revoked_at,
        })


class CourseViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CourseSerializer
    parser_classes = [parsers.JSONParser, parsers.FormParser, parsers.MultiPartParser]

    def get_permissions(self):
        if self.action in ['upload_materials', 'delete_mind_map']:
            return [IsAdminRole()]
        return [permissions.IsAuthenticated()]

    def get_throttles(self):
        self.throttle_scope = 'upload' if self.action == 'upload_materials' else None
        return super().get_throttles()

    def get_queryset(self):
        queryset = Course.objects.select_related('camp').prefetch_related('resources')
        camp = active_camp()
        if camp:
            queryset = queryset.filter(camp=camp)
        else:
            queryset = queryset.none()
        date = self.request.query_params.get('date')
        if date:
            queryset = queryset.filter(date=date)
        return queryset

    @action(detail=True, methods=['post'], url_path='materials')
    def upload_materials(self, request, pk=None):
        course = self.get_object()
        mind_map = request.FILES.get('mind_map')
        resource_files = request.FILES.getlist('resources')
        if not mind_map and not resource_files:
            return Response({'detail': '请选择思维导图或课程资料'}, status=status.HTTP_400_BAD_REQUEST)

        existing_count = course.resources.count()
        if existing_count + len(resource_files) > settings.COURSE_RESOURCE_MAX_FILES:
            return Response(
                {'resources': f'每门课程最多上传 {settings.COURSE_RESOURCE_MAX_FILES} 个资料文件'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        upload_size = (mind_map.size if mind_map else 0) + sum(item.size for item in resource_files)
        if upload_size > settings.COURSE_MATERIAL_MAX_REQUEST_SIZE:
            return Response(
                {'detail': '单次上传总大小不能超过 200MB，请分批添加课程资料'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        mind_map_content_type_value = ''
        try:
            if mind_map:
                validate_course_mind_map_file(mind_map)
                mind_map_content_type_value = course_mind_map_content_type(mind_map)
            for resource_file in resource_files:
                validate_course_resource_file(resource_file)
        except DjangoValidationError as exc:
            return Response({'detail': exc.messages[0]}, status=status.HTTP_400_BAD_REQUEST)

        old_mind_map_name = course.mind_map.name if course.mind_map else ''
        saved_files = []
        try:
            with transaction.atomic():
                if mind_map:
                    original_name = safe_original_filename(mind_map.name)
                    course.mind_map.save(original_name, mind_map, save=False)
                    saved_files.append((course.mind_map.storage, course.mind_map.name))
                    course.mind_map_original_filename = original_name
                    course.mind_map_content_type = mind_map_content_type_value
                    course.mind_map_file_size = mind_map.size
                    course.save(update_fields=[
                        'mind_map',
                        'mind_map_original_filename',
                        'mind_map_content_type',
                        'mind_map_file_size',
                    ])

                for resource_file in resource_files:
                    original_name = safe_original_filename(resource_file.name)
                    resource = CourseResource(
                        course=course,
                        original_filename=original_name,
                        content_type=course_resource_content_type(original_name),
                        file_size=resource_file.size,
                        created_by=request.user,
                    )
                    resource.file.save(original_name, resource_file, save=False)
                    saved_files.append((resource.file.storage, resource.file.name))
                    resource.save()
        except Exception:
            for storage_backend, stored_name in saved_files:
                storage_backend.delete(stored_name)
            raise

        if mind_map and old_mind_map_name and old_mind_map_name != course.mind_map.name:
            course.mind_map.storage.delete(old_mind_map_name)

        course = self.get_queryset().get(pk=course.pk)
        return Response(CourseSerializer(course, context={'request': request}).data)

    @action(detail=True, methods=['delete'], url_path='mind-map')
    def delete_mind_map(self, request, pk=None):
        course = self.get_object()
        if not course.mind_map:
            return Response({'detail': '该课程没有思维导图'}, status=status.HTTP_404_NOT_FOUND)

        storage_backend = course.mind_map.storage
        stored_name = course.mind_map.name
        course.mind_map = None
        course.mind_map_original_filename = ''
        course.mind_map_content_type = ''
        course.mind_map_file_size = 0
        course.save(update_fields=[
            'mind_map',
            'mind_map_original_filename',
            'mind_map_content_type',
            'mind_map_file_size',
        ])
        storage_backend.delete(stored_name)
        course = self.get_queryset().get(pk=course.pk)
        return Response(CourseSerializer(course, context={'request': request}).data)

    @action(detail=True, methods=['get'], url_path='mind-map-file')
    def mind_map_file(self, request, pk=None):
        course = self.get_object()
        return protected_course_file_response(
            course.mind_map,
            course.mind_map_original_filename or 'mind-map',
            course.mind_map_content_type,
            course.mind_map_file_size,
            attachment=False,
        )


class CourseResourceViewSet(mixins.DestroyModelMixin, viewsets.GenericViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def get_permissions(self):
        if self.action == 'destroy':
            return [IsAdminRole()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        queryset = CourseResource.objects.select_related('course', 'course__camp')
        camp = active_camp()
        return queryset.filter(course__camp=camp) if camp else queryset.none()

    def destroy(self, request, *args, **kwargs):
        resource = self.get_object()
        course_id = resource.course_id
        resource.delete()
        course = Course.objects.prefetch_related('resources').get(pk=course_id)
        return Response(CourseSerializer(course, context={'request': request}).data)

    @action(detail=True, methods=['get'], url_path='file')
    def file(self, request, pk=None):
        resource = self.get_object()
        return protected_course_file_response(
            resource.file,
            resource.original_filename,
            resource.content_type,
            resource.file_size,
            attachment=resource.content_type != 'application/pdf',
        )


class WorkViewSet(viewsets.ModelViewSet):
    serializer_class = WorkSerializer
    parser_classes = [parsers.JSONParser, parsers.FormParser, parsers.MultiPartParser]

    def get_permissions(self):
        if self.action in ['approve', 'reject', 'pending', 'bulk_review', 'review_logs']:
            return [IsAdminRole()]
        if self.action in ['create', 'like', 'vote', 'my', 'file', 'update', 'partial_update', 'destroy']:
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
        if self.action == 'file':
            profile = getattr(self.request.user, 'profile', None)
            is_admin = self.request.user.is_staff or getattr(profile, 'role', None) == Profile.Role.ADMIN
            if not is_admin:
                queryset = queryset.filter(Q(status=Work.Status.APPROVED) | Q(author=self.request.user))
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

    @action(detail=True, methods=['get'], url_path='file')
    def file(self, request, pk=None):
        work = self.get_object()
        if work.media_type != Work.MediaType.HTML or not work.protected_attachment:
            raise Http404('文件不存在')
        return protected_course_file_response(
            work.protected_attachment,
            work.original_filename or f'{work.title}.html',
            'application/octet-stream',
            work.file_size,
            attachment=True,
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
        profile_filters = (
            Q(name__icontains=keyword)
            | Q(workplace__icontains=keyword)
            | Q(mbti__icontains=keyword)
            | Q(zodiac__icontains=keyword)
            | Q(user__username__icontains=keyword)
        )
        group_match = re.fullmatch(r'(?:第\s*)?([1-6])(?:\s*组)?', keyword)
        if group_match:
            profile_filters |= Q(training_group=group_match.group(1))
        profiles = (
            Profile.objects.select_related('user')
            .filter(profile_filters)
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
        max_upload_size = (
            settings.WORK_HTML_MAX_UPLOAD_SIZE
            if media_type == Work.MediaType.HTML
            else settings.WORK_MAX_UPLOAD_SIZE
        )
        camp = active_camp()

        if not camp:
            return Response({'camp': '当前没有可投稿的培训期'}, status=status.HTTP_400_BAD_REQUEST)
        if not window_is_open(camp.submission_starts_at, camp.submission_ends_at):
            return Response({'camp': '当前培训期不在投稿时间内'}, status=status.HTTP_400_BAD_REQUEST)
        if not file_name:
            return Response({'file_name': '文件名不能为空'}, status=status.HTTP_400_BAD_REQUEST)
        if not media_type:
            return Response({'content_type': '仅支持图片、PDF、HTML、MP4、WebM 和 MOV 视频'}, status=status.HTTP_400_BAD_REQUEST)
        if media_type == Work.MediaType.HTML and not is_html_filename(file_name):
            return Response({'file_name': 'HTML 文件扩展名必须是 .html 或 .htm'}, status=status.HTTP_400_BAD_REQUEST)
        if media_type == Work.MediaType.HTML and (
            not total_size or total_size <= 0 or total_size > settings.WORK_HTML_MAX_UPLOAD_SIZE
        ):
            return Response({'total_size': 'HTML 文件必须大于 0 且不能超过 20MB'}, status=status.HTTP_400_BAD_REQUEST)
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
            'max_size': max_upload_size,
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
            if upload.media_type == Work.MediaType.HTML:
                upload.protected_file.save(final_name, File(file_obj), save=False)
            else:
                upload.file.save(final_name, File(file_obj), save=False)
        upload.status = ChunkedUpload.Status.COMPLETED
        upload.sha256 = actual_sha256
        upload.save(update_fields=['file', 'protected_file', 'sha256', 'status', 'updated_at'])
        shutil.rmtree(chunk_dir, ignore_errors=True)
        return self.response_for_upload(upload)

    @staticmethod
    def response_for_upload(upload):
        return Response({
            'upload_id': str(upload.upload_id),
            'file': upload.file.url if upload.file else '',
            'protected': bool(upload.protected_file),
            'file_name': upload.file_name,
            'content_type': upload.content_type,
            'media_type': upload.media_type,
            'total_size': upload.total_size,
            'sha256': upload.sha256,
            'expires_at': upload.expires_at,
        })
