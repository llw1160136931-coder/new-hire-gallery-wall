from django.contrib.auth.models import User
from django.conf import settings
from django.db.models import Count
from rest_framework import serializers

from .models import ChunkedUpload, Course, Like, Profile, Vote, Work, WorkImage, WorkReviewLog


MAX_WORK_IMAGES = 10


ALLOWED_ATTACHMENT_TYPES = {
    'application/pdf': Work.MediaType.PDF,
    'video/mp4': Work.MediaType.VIDEO,
    'video/webm': Work.MediaType.VIDEO,
    'video/quicktime': Work.MediaType.VIDEO,
    'image/jpeg': Work.MediaType.IMAGE,
    'image/png': Work.MediaType.IMAGE,
    'image/gif': Work.MediaType.IMAGE,
    'image/webp': Work.MediaType.IMAGE,
}


def media_type_from_content_type(content_type):
    return ALLOWED_ATTACHMENT_TYPES.get(content_type)


def is_image_content_type(content_type):
    return media_type_from_content_type(content_type) == Work.MediaType.IMAGE


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
    gender_label = serializers.CharField(source='get_gender_display', read_only=True)

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
            'gender_label',
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
            'topic',
            'teacher',
            'room',
            'content',
            'date',
            'start_time',
            'end_time',
            'status',
            'status_label',
            'sort_order',
        ]


class WorkImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkImage
        fields = ['id', 'image', 'order']


class WorkSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source='author.profile.name', read_only=True)
    author_avatar = serializers.ImageField(source='author.profile.avatar', read_only=True)
    work_type_label = serializers.CharField(source='get_work_type_display', read_only=True)
    media_type_label = serializers.CharField(source='get_media_type_display', read_only=True)
    status_label = serializers.CharField(source='get_status_display', read_only=True)
    like_count = serializers.IntegerField(read_only=True)
    vote_count = serializers.IntegerField(read_only=True)
    upload_id = serializers.UUIDField(write_only=True, required=False)
    images = WorkImageSerializer(source='gallery_images', many=True, read_only=True)

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
            'images',
            'attachment',
            'media_type',
            'media_type_label',
            'original_filename',
            'content_type',
            'file_size',
            'upload_id',
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
            'media_type',
            'original_filename',
            'content_type',
            'file_size',
            'created_at',
            'updated_at',
        ]

    def validate(self, attrs):
        upload_id = attrs.get('upload_id')
        attachment = attrs.get('attachment')
        image = attrs.get('image')
        gallery_images = self.get_uploaded_gallery_images()

        if len(gallery_images) > MAX_WORK_IMAGES:
            raise serializers.ValidationError({'images': f'最多只能上传 {MAX_WORK_IMAGES} 张图片'})

        if gallery_images and (upload_id or attachment or image):
            raise serializers.ValidationError({'images': '多图作品不能同时上传 PDF、视频或单张图片字段'})

        if upload_id:
            request = self.context.get('request')
            upload = ChunkedUpload.objects.filter(
                upload_id=upload_id,
                owner=request.user,
                status=ChunkedUpload.Status.COMPLETED,
            ).first()
            if not upload:
                raise serializers.ValidationError({'upload_id': '上传文件不存在或尚未合并完成'})
            self.context['chunked_upload'] = upload

        for uploaded_image in gallery_images:
            if uploaded_image.size > settings.WORK_MAX_UPLOAD_SIZE:
                raise serializers.ValidationError({'images': '单张图片不能超过 500MB'})
            content_type = getattr(uploaded_image, 'content_type', '')
            if not is_image_content_type(content_type):
                raise serializers.ValidationError({'images': '多图上传只支持 JPG、PNG、GIF 或 WebP 图片'})

        if gallery_images:
            self.context['gallery_images'] = gallery_images

        for uploaded_file in [attachment, image]:
            if not uploaded_file:
                continue
            if uploaded_file.size > settings.WORK_MAX_UPLOAD_SIZE:
                raise serializers.ValidationError({'attachment': '文件不能超过 500MB'})
            content_type = getattr(uploaded_file, 'content_type', '')
            if not media_type_from_content_type(content_type):
                raise serializers.ValidationError({'attachment': '仅支持图片、PDF、MP4、WebM 和 MOV 视频'})

        return attrs

    def get_uploaded_gallery_images(self):
        request = self.context.get('request')
        if not request:
            return []
        return list(request.FILES.getlist('images'))

    def create(self, validated_data):
        validated_data.pop('upload_id', None)
        chunked_upload = self.context.get('chunked_upload')
        gallery_images = self.context.get('gallery_images')
        instance = super().create(validated_data)
        self.apply_attachment_metadata(instance, chunked_upload)
        self.apply_gallery_images(instance, gallery_images)
        return instance

    def update(self, instance, validated_data):
        validated_data.pop('upload_id', None)
        chunked_upload = self.context.get('chunked_upload')
        gallery_images = self.context.get('gallery_images')
        instance = super().update(instance, validated_data)
        self.apply_attachment_metadata(instance, chunked_upload)
        self.apply_gallery_images(instance, gallery_images)
        return instance

    def apply_gallery_images(self, instance, gallery_images=None):
        if gallery_images is None:
            return

        instance.gallery_images.all().delete()
        for order, uploaded_image in enumerate(gallery_images):
            WorkImage.objects.create(work=instance, image=uploaded_image, order=order)

        if gallery_images:
            instance.attachment = None
            instance.image = None
            instance.image_url = ''
            instance.media_type = Work.MediaType.IMAGE
            instance.original_filename = gallery_images[0].name
            instance.content_type = getattr(gallery_images[0], 'content_type', '') or instance.content_type
            instance.file_size = sum(getattr(uploaded_image, 'size', 0) for uploaded_image in gallery_images)
            instance.save(update_fields=[
                'attachment',
                'image',
                'image_url',
                'media_type',
                'original_filename',
                'content_type',
                'file_size',
            ])

    def apply_attachment_metadata(self, instance, chunked_upload=None):
        if chunked_upload:
            instance.gallery_images.all().delete()
            instance.attachment = chunked_upload.file
            instance.media_type = chunked_upload.media_type
            instance.original_filename = chunked_upload.file_name
            instance.content_type = chunked_upload.content_type
            instance.file_size = chunked_upload.total_size
            instance.save(update_fields=['attachment', 'media_type', 'original_filename', 'content_type', 'file_size'])
            return

        uploaded_file = instance.attachment or instance.image
        if uploaded_file:
            instance.gallery_images.all().delete()
            content_type = getattr(uploaded_file.file, 'content_type', '') or instance.content_type
            media_type = media_type_from_content_type(content_type) or instance.media_type
            instance.media_type = media_type
            instance.original_filename = instance.original_filename or uploaded_file.name.split('/')[-1]
            instance.content_type = content_type
            instance.file_size = getattr(uploaded_file, 'size', 0) or instance.file_size
            instance.save(update_fields=['media_type', 'original_filename', 'content_type', 'file_size'])
        elif instance.gallery_images.exists():
            instance.media_type = Work.MediaType.IMAGE
            instance.save(update_fields=['media_type'])
        elif instance.image_url or instance.link:
            instance.media_type = Work.MediaType.LINK
            instance.save(update_fields=['media_type'])

    @staticmethod
    def setup_eager_loading(queryset):
        return queryset.select_related('author__profile').prefetch_related('gallery_images').annotate(
            like_count=Count('likes', distinct=True),
            vote_count=Count('votes', distinct=True),
        )


class ReviewSerializer(serializers.Serializer):
    reject_reason = serializers.CharField(required=False, allow_blank=True)


class BulkReviewSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=WorkReviewLog.Action.values)
    ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
        max_length=100,
    )
    reject_reason = serializers.CharField(required=False, allow_blank=True)


class WorkReviewLogSerializer(serializers.ModelSerializer):
    reviewer_name = serializers.CharField(source='reviewer.profile.name', read_only=True)
    reviewer_username = serializers.CharField(source='reviewer.username', read_only=True)
    action_label = serializers.CharField(source='get_action_display', read_only=True)
    work_title = serializers.CharField(source='work.title', read_only=True)
    author_name = serializers.CharField(source='work.author.profile.name', read_only=True)

    class Meta:
        model = WorkReviewLog
        fields = [
            'id',
            'work',
            'work_title',
            'author_name',
            'reviewer_name',
            'reviewer_username',
            'action',
            'action_label',
            'reason',
            'created_at',
        ]


class LeaderboardSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source='author.profile.name', read_only=True)
    like_count = serializers.IntegerField(read_only=True)
    vote_count = serializers.IntegerField(read_only=True)
    score = serializers.IntegerField(read_only=True)

    class Meta:
        model = Work
        fields = ['id', 'title', 'work_type', 'author_name', 'like_count', 'vote_count', 'score']


class PublicProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    gender_label = serializers.CharField(source='get_gender_display', read_only=True)

    class Meta:
        model = Profile
        fields = ['username', 'name', 'avatar', 'school', 'mbti', 'zodiac', 'gender', 'gender_label', 'bio']
