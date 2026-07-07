from django.contrib import admin

from .models import Course, Like, Profile, Vote, Work


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'role', 'school', 'gender', 'updated_at']
    list_filter = ['role', 'gender']
    search_fields = ['name', 'user__username', 'school']


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ['date', 'start_time', 'end_time', 'title', 'teacher', 'room', 'status']
    list_filter = ['date', 'status']
    search_fields = ['title', 'teacher', 'room']


@admin.register(Work)
class WorkAdmin(admin.ModelAdmin):
    list_display = ['title', 'author', 'work_type', 'status', 'created_at', 'reviewed_at']
    list_filter = ['work_type', 'status']
    search_fields = ['title', 'description', 'author__username', 'author__profile__name']


admin.site.register(Like)
admin.site.register(Vote)

# Register your models here.
