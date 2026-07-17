import uuid
from pathlib import Path


HTML_EXTENSIONS = {'.html', '.htm'}


def is_html_filename(filename):
    return Path(str(filename or '')).suffix.lower() in HTML_EXTENSIONS


def protected_work_html_upload_to(instance, filename):
    """Keep executable HTML outside MEDIA_ROOT and behind the authenticated API."""
    extension = Path(str(filename or '')).suffix.lower()
    if extension not in HTML_EXTENSIONS:
        extension = '.html'
    return f'works/html/{uuid.uuid4().hex}{extension}'
