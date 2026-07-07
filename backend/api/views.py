from django.db.models import Count, F
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Course, Like, Work, Vote
from .permissions import IsAdminRole
from .serializers import (
    CourseSerializer,
    LeaderboardSerializer,
    ProfileSerializer,
    RegisterSerializer,
    ReviewSerializer,
    WorkSerializer,
)


class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class MeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

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

    def get_permissions(self):
        if self.action in ['approve', 'reject', 'pending']:
            return [IsAdminRole()]
        if self.action in ['create', 'like', 'vote', 'my']:
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
        return queryset

    def perform_create(self, serializer):
        serializer.save(author=self.request.user, status=Work.Status.PENDING)

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
        work.status = Work.Status.APPROVED
        work.reject_reason = ''
        work.reviewed_by = request.user
        work.reviewed_at = timezone.now()
        work.save(update_fields=['status', 'reject_reason', 'reviewed_by', 'reviewed_at', 'updated_at'])
        return Response(self.get_serializer(work).data)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        serializer = ReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reject_reason = serializer.validated_data.get('reject_reason', '').strip()
        if not reject_reason:
            return Response({'reject_reason': '打回时必须填写原因'}, status=status.HTTP_400_BAD_REQUEST)
        work = self.get_object()
        work.status = Work.Status.REJECTED
        work.reject_reason = reject_reason
        work.reviewed_by = request.user
        work.reviewed_at = timezone.now()
        work.save(update_fields=['status', 'reject_reason', 'reviewed_by', 'reviewed_at', 'updated_at'])
        return Response(self.get_serializer(work).data)

    @action(detail=True, methods=['post'])
    def like(self, request, pk=None):
        work = self.get_object()
        Like.objects.get_or_create(user=request.user, work=work)
        return Response({'detail': 'liked'}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def vote(self, request, pk=None):
        work = self.get_object()
        Vote.objects.get_or_create(user=request.user, work=work)
        return Response({'detail': 'voted'}, status=status.HTTP_200_OK)


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
