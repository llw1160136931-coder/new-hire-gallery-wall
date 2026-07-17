"""Fail-closed verification for an isolated load-test backend."""

from __future__ import annotations

import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


EXPECTED_CAMP_SLUG = 'loadtest_camp'
MAX_IDENTITY_BYTES = 16 * 1024
TARGET_ID_PATTERN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$')


class IdentityVerificationError(RuntimeError):
    """The target did not prove it is the intended load-test environment."""


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        return None


def validate_target_id(target_id: str) -> str:
    normalized = str(target_id or '').strip()
    if not TARGET_ID_PATTERN.fullmatch(normalized):
        raise IdentityVerificationError('expected target ID must contain 8-128 safe characters')
    return normalized


def identity_url(host: str, api_prefix: str = '/api') -> str:
    parsed = urlsplit(str(host or '').strip())
    if (
        parsed.scheme not in {'http', 'https'}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise IdentityVerificationError('target host must be a plain http(s) origin without credentials or query')
    prefix = '/' + str(api_prefix or '/api').strip('/')
    path = f'{prefix}/loadtest/identity/'
    return urlunsplit((parsed.scheme, parsed.netloc, path, '', ''))


def fetch_and_validate_identity(
    host: str,
    expected_target_id: str,
    *,
    api_prefix: str = '/api',
    timeout: float = 5.0,
) -> dict:
    """Fetch a non-secret identity document and validate every safety field."""

    expected = validate_target_id(expected_target_id)
    url = identity_url(host, api_prefix)
    request = Request(
        url,
        headers={
            'Accept': 'application/json',
            'Accept-Encoding': 'identity',
            'Cache-Control': 'no-cache',
            'User-Agent': 'new-hire-gallery-loadtest-identity/1',
        },
        method='GET',
    )
    opener = build_opener(_RejectRedirects())
    try:
        with opener.open(request, timeout=timeout) as response:
            status = getattr(response, 'status', response.getcode())
            content_type = response.headers.get_content_type()
            raw = response.read(MAX_IDENTITY_BYTES + 1)
    except HTTPError as exc:
        raise IdentityVerificationError(
            f'identity endpoint rejected the request with HTTP {exc.code}; redirects are not accepted'
        ) from exc
    except (OSError, URLError) as exc:
        raise IdentityVerificationError('identity endpoint could not be reached safely') from exc

    if status != 200:
        raise IdentityVerificationError(f'identity endpoint returned HTTP {status}, expected 200')
    if content_type != 'application/json':
        raise IdentityVerificationError('identity endpoint did not return application/json')
    if len(raw) > MAX_IDENTITY_BYTES:
        raise IdentityVerificationError('identity endpoint response was unexpectedly large')
    try:
        payload = json.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IdentityVerificationError('identity endpoint returned invalid JSON') from exc
    if not isinstance(payload, dict):
        raise IdentityVerificationError('identity endpoint returned the wrong JSON shape')
    if payload.get('schema_version') != 1:
        raise IdentityVerificationError('identity endpoint schema version is not supported')
    if payload.get('loadtest_mode') is not True:
        raise IdentityVerificationError('target backend is not in load-test mode')
    if payload.get('target_id') != expected:
        raise IdentityVerificationError('target backend ID does not match the expected load-test target')
    if payload.get('active_camp_slug') != EXPECTED_CAMP_SLUG:
        raise IdentityVerificationError(
            f'active camp must be exactly {EXPECTED_CAMP_SLUG!r} before load-test writes'
        )
    return payload
