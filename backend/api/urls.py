from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenVerifyView

from .views import (
    AdminAttendanceGenerateView,
    AdminAttendanceOverviewView,
    CourseViewSet,
    CurrentTrainingCampView,
    LeaderboardView,
    MeView,
    PopularTagView,
    RegisterView,
    SearchView,
    StudentAttendanceCheckInView,
    StudentAttendanceTodayView,
    ThrottledTokenObtainPairView,
    ThrottledTokenRefreshView,
    UploadChunkView,
    UploadCompleteView,
    UploadInitView,
    WorkViewSet,
)

router = DefaultRouter()
router.register('courses', CourseViewSet, basename='course')
router.register('works', WorkViewSet, basename='work')

urlpatterns = [
    path('auth/register/', RegisterView.as_view(), name='register'),
    path('auth/token/', ThrottledTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/token/refresh/', ThrottledTokenRefreshView.as_view(), name='token_refresh'),
    path('auth/token/verify/', TokenVerifyView.as_view(), name='token_verify'),
    path('me/', MeView.as_view(), name='me'),
    path('attendance/today/', StudentAttendanceTodayView.as_view(), name='attendance-today'),
    path('attendance/check-in/', StudentAttendanceCheckInView.as_view(), name='attendance-check-in'),
    path('attendance/admin/overview/', AdminAttendanceOverviewView.as_view(), name='attendance-admin-overview'),
    path('attendance/admin/generate/', AdminAttendanceGenerateView.as_view(), name='attendance-admin-generate'),
    path('camps/current/', CurrentTrainingCampView.as_view(), name='current-training-camp'),
    path('leaderboard/', LeaderboardView.as_view(), name='leaderboard'),
    path('tags/popular/', PopularTagView.as_view(), name='popular-tags'),
    path('search/', SearchView.as_view(), name='search'),
    path('uploads/init/', UploadInitView.as_view(), name='upload-init'),
    path('uploads/<uuid:upload_id>/chunk/', UploadChunkView.as_view(), name='upload-chunk'),
    path('uploads/<uuid:upload_id>/complete/', UploadCompleteView.as_view(), name='upload-complete'),
    path('', include(router.urls)),
]
