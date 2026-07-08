from django.contrib import admin

from .models import ChunkedUpload, Course, Like, Profile, Vote, Work


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'role', 'school', 'gender', 'updated_at']
    list_filter = ['role', 'gender']
    search_fields = ['name', 'user__username', 'school']


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ['date', 'start_time', 'end_time', 'topic', 'title', 'teacher', 'room', 'status']
    list_filter = ['date', 'status', 'topic']
    search_fields = ['title', 'topic', 'teacher', 'room', 'content']


@admin.register(Work)
class WorkAdmin(admin.ModelAdmin):
    list_display = ['title', 'author', 'work_type', 'media_type', 'status', 'file_size', 'created_at', 'reviewed_at']
    list_filter = ['work_type', 'media_type', 'status']
    search_fields = ['title', 'description', 'author__username', 'author__profile__name']


@admin.register(ChunkedUpload)
class ChunkedUploadAdmin(admin.ModelAdmin):
    list_display = ['file_name', 'owner', 'media_type', 'status', 'total_size', 'total_chunks', 'created_at']
    list_filter = ['media_type', 'status']
    search_fields = ['file_name', 'owner__username']
    readonly_fields = ['upload_id', 'uploaded_chunks', 'created_at', 'updated_at']


admin.site.register(Like)
admin.site.register(Vote)

# Register your models here.
