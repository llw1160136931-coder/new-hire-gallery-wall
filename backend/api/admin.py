from django.contrib import admin

from .models import ChunkedUpload, Course, Like, Profile, Tag, TrainingCamp, Vote, Work, WorkImage, WorkReviewLog


@admin.register(TrainingCamp)
class TrainingCampAdmin(admin.ModelAdmin):
    list_display = ['name', 'start_date', 'end_date', 'vote_limit', 'is_active']
    list_filter = ['is_active', 'start_date']
    search_fields = ['name', 'slug']


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ['name', 'normalized_name', 'created_at']
    search_fields = ['name', 'normalized_name']


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'role', 'school', 'gender', 'updated_at']
    list_filter = ['role', 'gender']
    search_fields = ['name', 'user__username', 'school']


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ['camp', 'date', 'start_time', 'end_time', 'topic', 'title', 'teacher', 'room', 'status']
    list_filter = ['camp', 'date', 'status', 'topic']
    search_fields = ['title', 'topic', 'teacher', 'room', 'content']


@admin.register(Work)
class WorkAdmin(admin.ModelAdmin):
    list_display = ['title', 'camp', 'author', 'work_type', 'media_type', 'status', 'file_size', 'created_at', 'reviewed_at']
    list_filter = ['camp', 'work_type', 'media_type', 'status']
    search_fields = ['title', 'description', 'author__username', 'author__profile__name']
    filter_horizontal = ['tags']
    inlines = []


class WorkImageInline(admin.TabularInline):
    model = WorkImage
    extra = 0
    fields = ['image', 'order', 'created_at']
    readonly_fields = ['created_at']


WorkAdmin.inlines = [WorkImageInline]


@admin.register(ChunkedUpload)
class ChunkedUploadAdmin(admin.ModelAdmin):
    list_display = ['file_name', 'camp', 'owner', 'media_type', 'status', 'total_size', 'total_chunks', 'expires_at']
    list_filter = ['media_type', 'status']
    search_fields = ['file_name', 'owner__username']
    readonly_fields = ['upload_id', 'uploaded_chunks', 'sha256', 'created_at', 'updated_at']


@admin.register(WorkReviewLog)
class WorkReviewLogAdmin(admin.ModelAdmin):
    list_display = ['work', 'reviewer', 'action', 'created_at']
    list_filter = ['action', 'created_at']
    search_fields = ['work__title', 'reviewer__username', 'reason']
    readonly_fields = ['work', 'reviewer', 'action', 'reason', 'created_at']


admin.site.register(Like)
admin.site.register(Vote)

# Register your models here.
