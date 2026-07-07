from django.contrib.auth.models import User
from django.db.models import Count
from rest_framework import serializers

from .models import Course, Like, Profile, Vote, Work


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    name = serializers.CharField(max_length=50)

    class Meta:
        model = User
        fields = ['id', 'username', 'password', 'name']

    def create(self, validated_data):
        name = validated_data.pop('name')
        password = validated_data.pop('password')
        user = User(username=validated_data['username'])
        user.set_password(password)
        user.save()
        profile, _ = Profile.objects.get_or_create(user=user, defaults={'name': name})
        profile.name = name
        profile.save(update_fields=['name'])
        return user


class ProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = Profile
        fields = [
            'username',
            'role',
            'name',
            'avatar',
            'school',
            'mbti',
            'zodiac',
            'gender',
            'bio',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['role', 'created_at', 'updated_at']


class CourseSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = Course
        fields = [
            'id',
            'title',
            'teacher',
            'room',
            'date',
            'start_time',
            'end_time',
            'status',
            'status_label',
            'sort_order',
        ]


class WorkSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source='author.profile.name', read_only=True)
    author_avatar = serializers.ImageField(source='author.profile.avatar', read_only=True)
    work_type_label = serializers.CharField(source='get_work_type_display', read_only=True)
    status_label = serializers.CharField(source='get_status_display', read_only=True)
    like_count = serializers.IntegerField(read_only=True)
    vote_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Work
        fields = [
            'id',
            'author',
            'author_name',
            'author_avatar',
            'title',
            'work_type',
            'work_type_label',
            'image',
            'image_url',
            'link',
            'description',
            'status',
            'status_label',
            'reject_reason',
            'reviewed_by',
            'reviewed_at',
            'like_count',
            'vote_count',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'author',
            'status',
            'reject_reason',
            'reviewed_by',
            'reviewed_at',
            'created_at',
            'updated_at',
        ]

    @staticmethod
    def setup_eager_loading(queryset):
        return queryset.select_related('author__profile').annotate(
            like_count=Count('likes', distinct=True),
            vote_count=Count('votes', distinct=True),
        )


class ReviewSerializer(serializers.Serializer):
    reject_reason = serializers.CharField(required=False, allow_blank=True)


class LeaderboardSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source='author.profile.name', read_only=True)
    like_count = serializers.IntegerField(read_only=True)
    vote_count = serializers.IntegerField(read_only=True)
    score = serializers.IntegerField(read_only=True)

    class Meta:
        model = Work
        fields = ['id', 'title', 'work_type', 'author_name', 'like_count', 'vote_count', 'score']
