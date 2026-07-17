import mimetypes
import uuid
import zipfile
from pathlib import Path, PurePosixPath

from django.conf import settings
from django.core.exceptions import ValidationError
from PIL import Image, UnidentifiedImageError


COURSE_MIND_MAP_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}
COURSE_RESOURCE_EXTENSIONS = {'.pdf', '.pptx'}
COURSE_RESOURCE_CONTENT_TYPES = {
    '.pdf': 'application/pdf',
    '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
}
COURSE_MIND_MAP_CONTENT_TYPES = {
    'JPEG': 'image/jpeg',
    'PNG': 'image/png',
    'WEBP': 'image/webp',
}


def normalized_extension(filename):
    return Path(filename or '').suffix.lower()


def course_mind_map_upload_to(instance, filename):
    extension = normalized_extension(filename)
    return f'courses/{instance.pk}/mind-maps/{uuid.uuid4().hex}{extension}'


def course_resource_upload_to(instance, filename):
    extension = normalized_extension(filename)
    return f'courses/{instance.course_id}/resources/{uuid.uuid4().hex}{extension}'


def _reset_file(uploaded_file):
    try:
        uploaded_file.seek(0)
    except (AttributeError, OSError):
        pass


def validate_course_mind_map_file(uploaded_file):
    extension = normalized_extension(uploaded_file.name)
    if extension not in COURSE_MIND_MAP_EXTENSIONS:
        raise ValidationError('思维导图仅支持 JPG、PNG 或 WebP 图片。')
    if uploaded_file.size > settings.COURSE_MIND_MAP_MAX_SIZE:
        raise ValidationError('思维导图不能超过 10MB。')

    try:
        _reset_file(uploaded_file)
        with Image.open(uploaded_file) as image:
            pixel_count = image.width * image.height
            max_pixels = settings.COURSE_MIND_MAP_MAX_PIXELS
            if pixel_count > max_pixels:
                raise ValidationError(
                    f'思维导图分辨率过高：{image.width} × {image.height}（{pixel_count:,} 像素），'
                    f'服务器上限为 {max_pixels:,} 像素。请等比例缩小后重试。'
                )
            image.verify()
            image_format = image.format
        if image_format not in COURSE_MIND_MAP_CONTENT_TYPES:
            raise ValidationError('思维导图图片格式不正确。')
        if extension in {'.jpg', '.jpeg'} and image_format != 'JPEG':
            raise ValidationError('思维导图文件扩展名与真实格式不一致。')
        if extension == '.png' and image_format != 'PNG':
            raise ValidationError('思维导图文件扩展名与真实格式不一致。')
        if extension == '.webp' and image_format != 'WEBP':
            raise ValidationError('思维导图文件扩展名与真实格式不一致。')
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError, ValueError) as exc:
        raise ValidationError('思维导图不是有效图片或文件已经损坏。') from exc
    finally:
        _reset_file(uploaded_file)


def _validate_pptx(uploaded_file):
    try:
        _reset_file(uploaded_file)
        with zipfile.ZipFile(uploaded_file) as archive:
            members = archive.infolist()
            if len(members) > settings.COURSE_PPTX_MAX_MEMBERS:
                raise ValidationError('PPTX 文件内部条目过多。')
            names = {member.filename for member in members}
            if '[Content_Types].xml' not in names or 'ppt/presentation.xml' not in names:
                raise ValidationError('PPTX 文件结构不完整或格式不正确。')

            total_uncompressed = 0
            for member in members:
                path = PurePosixPath(member.filename)
                if path.is_absolute() or '..' in path.parts:
                    raise ValidationError('PPTX 文件包含不安全的路径。')
                if member.flag_bits & 0x1:
                    raise ValidationError('暂不支持加密的 PPTX 文件。')
                total_uncompressed += member.file_size
                if member.compress_size and member.file_size > member.compress_size * 200:
                    raise ValidationError('PPTX 文件压缩比例异常。')

            if total_uncompressed > settings.COURSE_PPTX_MAX_UNCOMPRESSED_SIZE:
                raise ValidationError('PPTX 解压后的内容过大。')
    except zipfile.BadZipFile as exc:
        raise ValidationError('PPTX 文件已损坏或真实格式不正确。') from exc
    finally:
        _reset_file(uploaded_file)


def validate_course_resource_file(uploaded_file):
    extension = normalized_extension(uploaded_file.name)
    if extension not in COURSE_RESOURCE_EXTENSIONS:
        raise ValidationError('课程资料仅支持 PDF 或 PPTX。')
    if uploaded_file.size > settings.COURSE_RESOURCE_MAX_SIZE:
        raise ValidationError('单个课程资料不能超过 100MB。')

    if extension == '.pdf':
        try:
            _reset_file(uploaded_file)
            if not uploaded_file.read(5).startswith(b'%PDF-'):
                raise ValidationError('PDF 文件真实格式不正确。')
        finally:
            _reset_file(uploaded_file)
    else:
        _validate_pptx(uploaded_file)


def course_mind_map_content_type(uploaded_file):
    try:
        _reset_file(uploaded_file)
        with Image.open(uploaded_file) as image:
            return COURSE_MIND_MAP_CONTENT_TYPES.get(image.format, 'application/octet-stream')
    finally:
        _reset_file(uploaded_file)


def course_resource_content_type(filename):
    extension = normalized_extension(filename)
    return COURSE_RESOURCE_CONTENT_TYPES.get(
        extension,
        mimetypes.guess_type(filename or '')[0] or 'application/octet-stream',
    )
