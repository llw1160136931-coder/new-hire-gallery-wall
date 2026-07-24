import uuid


def talent_profile_report_upload_to(instance, filename):
    """Store reports under an opaque, non-PII name in protected storage."""
    return f'talent-profiles/{instance.camp_id}/{uuid.uuid4().hex}.html'
