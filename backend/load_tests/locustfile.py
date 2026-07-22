"""Locust scenarios for the deployed new-hire gallery system.

This module deliberately has no credentials or test-media paths in source control.
Configure it with environment variables before starting Locust::

    LOADTEST_ACCOUNTS_CSV=/secure/accounts.csv
    LOADTEST_ASSETS_CSV=/secure/assets.csv
    LOADTEST_CONFIRM_WRITES=YES
    LOADTEST_ALLOW_NONTEST_READS=READ_ONLY
    LOADTEST_ENABLE_INTERACTIONS=1
    LOADTEST_ENABLE_UPLOADS=1

``accounts.csv`` must contain ``username,password`` columns. ``assets.csv`` must
contain ``kind,path`` columns, where ``kind`` is ``image`` or ``video``; an
optional ``content_type`` column may override MIME type detection. Relative asset
paths are resolved relative to the assets CSV.

For a small smoke test, one account and material paths may instead be supplied
with ``LOADTEST_USERNAME``, ``LOADTEST_PASSWORD``, ``LOADTEST_IMAGE_PATHS`` and
``LOADTEST_VIDEO_PATHS``. Path lists use the platform path separator (``:`` on
Linux, ``;`` on Windows).

Writes are disabled unless ``LOADTEST_CONFIRM_WRITES`` is exactly ``YES``.
Even then, mutating traffic is only allowed when the target host visibly looks
like a local/test/staging host. There is intentionally no production-write
bypass.
Read-only traffic to a non-test hostname is also rejected unless
``LOADTEST_ALLOW_NONTEST_READS`` is exactly ``READ_ONLY``.
HTTP 400 responses that represent explicitly named business outcomes
(duplicate like/vote or the per-user vote limit) are recorded under a separate
request name. HTTP 429
responses are always counted separately and are failures by default; set
``LOADTEST_ACCEPT_429=1`` only when deliberately measuring rate limiting. Server
errors are never accepted, regardless of configuration.
"""

from __future__ import annotations

import base64
import csv
import hashlib
import json
import logging
import mimetypes
import os
import random
import re
import threading
import time
import uuid
from collections import Counter, deque
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import urlsplit

from locust import HttpUser, between, events
from locust.exception import StopUser

try:
    from backend.load_tests.identity_guard import (
        IdentityVerificationError,
        fetch_and_validate_identity,
    )
except ModuleNotFoundError:  # Locust may put only this file's directory on sys.path.
    from identity_guard import IdentityVerificationError, fetch_and_validate_identity


LOGGER = logging.getLogger(__name__)
MIB = 1024 * 1024
VIDEO_CHUNK_BYTES = 8 * MIB


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, minimum: int = 0) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if value < minimum:
        raise RuntimeError(f"{name} must be at least {minimum}")
    return value


def _env_float(name: str, default: float, minimum: float = 0.0) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a number") from exc
    if value < minimum:
        raise RuntimeError(f"{name} must be at least {minimum}")
    return value


def _safe_run_id(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "-", value).strip("-_")
    return (normalized or "run")[:16]


API_PREFIX = "/" + os.environ.get("LOADTEST_API_PREFIX", "/api").strip("/")
WAIT_MIN = _env_float("LOADTEST_WAIT_MIN", 1.0, 0.0)
WAIT_MAX = _env_float("LOADTEST_WAIT_MAX", 4.0, WAIT_MIN)
RUN_ID = _safe_run_id(
    os.environ.get("LOADTEST_RUN_ID", datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S"))
)
SEARCH_TERM = os.environ.get("LOADTEST_SEARCH_TERM", "AI").strip() or "AI"
ACCEPT_429 = _env_bool("LOADTEST_ACCEPT_429", False)
WRITES_CONFIRMED = os.environ.get("LOADTEST_CONFIRM_WRITES", "").strip() == "YES"
NONTEST_READ_ACKNOWLEDGEMENT = os.environ.get("LOADTEST_ALLOW_NONTEST_READS", "").strip()
EXPECTED_TARGET_ID = os.environ.get("LOADTEST_EXPECTED_TARGET_ID", "").strip()
REQUIRE_TARGET_IDENTITY = _env_bool("LOADTEST_REQUIRE_TARGET_IDENTITY", False)
ENABLE_INTERACTIONS = WRITES_CONFIRMED and _env_bool("LOADTEST_ENABLE_INTERACTIONS", False)
ENABLE_UPLOADS = WRITES_CONFIRMED and _env_bool("LOADTEST_ENABLE_UPLOADS", False)
CLEANUP_CREATED = _env_bool("LOADTEST_CLEANUP_CREATED", True)
MEDIA_RANGE_BYTES = _env_int("LOADTEST_MEDIA_RANGE_BYTES", MIB, 1)
MEDIA_READ_LIMIT = _env_int("LOADTEST_MEDIA_READ_LIMIT_BYTES", 16 * MIB, 0)
IMAGES_PER_WORK = _env_int("LOADTEST_IMAGES_PER_WORK", 2, 1)
MAX_IMAGE_UPLOADS = _env_int("LOADTEST_MAX_IMAGE_UPLOADS_PER_USER", 1, 0)
MAX_VIDEO_UPLOADS = _env_int("LOADTEST_MAX_VIDEO_UPLOADS_PER_USER", 1, 0)

PUBLIC_USER_WEIGHT = _env_int("LOADTEST_PUBLIC_USER_WEIGHT", 3, 0)
AUTH_USER_WEIGHT = _env_int("LOADTEST_AUTH_USER_WEIGHT", 6, 0)
UPLOAD_USER_WEIGHT = _env_int("LOADTEST_UPLOAD_USER_WEIGHT", 1, 0)

BROWSE_TASK_WEIGHT = _env_int("LOADTEST_BROWSE_TASK_WEIGHT", 8, 1)
MEDIA_TASK_WEIGHT = _env_int("LOADTEST_MEDIA_TASK_WEIGHT", 3, 1)
SEARCH_TASK_WEIGHT = _env_int("LOADTEST_SEARCH_TASK_WEIGHT", 2, 1)
INTERACTION_TASK_WEIGHT = _env_int("LOADTEST_INTERACTION_TASK_WEIGHT", 2, 1)
IMAGE_UPLOAD_TASK_WEIGHT = _env_int("LOADTEST_IMAGE_UPLOAD_TASK_WEIGHT", 3, 1)
VIDEO_UPLOAD_TASK_WEIGHT = _env_int("LOADTEST_VIDEO_UPLOAD_TASK_WEIGHT", 1, 1)


def _api(path: str) -> str:
    return f"{API_PREFIX}/{path.lstrip('/')}"


@dataclass(frozen=True)
class Account:
    username: str
    password: str


@dataclass(frozen=True)
class Asset:
    kind: str
    path: Path
    content_type: str


def _load_accounts() -> list[Account]:
    accounts: list[Account] = []
    csv_value = os.environ.get("LOADTEST_ACCOUNTS_CSV", "").strip()
    username = os.environ.get("LOADTEST_USERNAME", "").strip()
    password = os.environ.get("LOADTEST_PASSWORD", "")

    if bool(username) != bool(password):
        raise RuntimeError("LOADTEST_USERNAME and LOADTEST_PASSWORD must be supplied together")
    if username:
        accounts.append(Account(username=username, password=password))

    if csv_value:
        csv_path = Path(csv_value).expanduser().resolve()
        if not csv_path.is_file():
            raise RuntimeError(f"Account CSV does not exist: {csv_path}")
        with csv_path.open("r", encoding="utf-8-sig", newline="") as source:
            reader = csv.DictReader(source)
            fields = {field.strip() for field in (reader.fieldnames or []) if field}
            if not {"username", "password"}.issubset(fields):
                raise RuntimeError("Account CSV must contain username,password columns")
            for line_number, row in enumerate(reader, start=2):
                row_username = (row.get("username") or "").strip()
                row_password = row.get("password") or ""
                enabled = (row.get("enabled") or "1").strip().lower()
                if enabled in {"0", "false", "no", "off"}:
                    continue
                if not row_username or not row_password:
                    raise RuntimeError(f"Account CSV row {line_number} has an empty username or password")
                accounts.append(Account(username=row_username, password=row_password))

    seen: set[str] = set()
    for account in accounts:
        if account.username in seen:
            raise RuntimeError(f"Duplicate username in load-test accounts: {account.username}")
        seen.add(account.username)
    return accounts


ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
ALLOWED_VIDEO_TYPES = {"video/mp4", "video/webm", "video/quicktime"}


def _asset_from_values(kind: str, path_value: str, content_type: str = "", *, base: Path | None = None) -> Asset:
    kind = kind.strip().lower()
    if kind not in {"image", "video"}:
        raise RuntimeError(f"Unsupported asset kind {kind!r}; expected image or video")
    path = Path(path_value.strip()).expanduser()
    if base is not None and not path.is_absolute():
        path = base / path
    path = path.resolve()
    if not path.is_file():
        raise RuntimeError(f"Load-test asset does not exist: {path}")
    guessed = mimetypes.guess_type(path.name)[0] or ""
    resolved_type = content_type.strip().lower() or guessed
    allowed = ALLOWED_IMAGE_TYPES if kind == "image" else ALLOWED_VIDEO_TYPES
    if resolved_type not in allowed:
        raise RuntimeError(f"Unsupported {kind} content type {resolved_type!r} for {path}")
    return Asset(kind=kind, path=path, content_type=resolved_type)


def _split_env_paths(value: str) -> Iterable[str]:
    for item in value.split(os.pathsep):
        stripped = item.strip()
        if stripped:
            yield stripped


def _load_assets() -> tuple[list[Asset], list[Asset]]:
    assets: list[Asset] = []
    csv_value = os.environ.get("LOADTEST_ASSETS_CSV", "").strip()
    if csv_value:
        csv_path = Path(csv_value).expanduser().resolve()
        if not csv_path.is_file():
            raise RuntimeError(f"Asset CSV does not exist: {csv_path}")
        with csv_path.open("r", encoding="utf-8-sig", newline="") as source:
            reader = csv.DictReader(source)
            fields = {field.strip() for field in (reader.fieldnames or []) if field}
            if not {"kind", "path"}.issubset(fields):
                raise RuntimeError("Asset CSV must contain kind,path columns")
            for line_number, row in enumerate(reader, start=2):
                try:
                    assets.append(
                        _asset_from_values(
                            row.get("kind") or "",
                            row.get("path") or "",
                            row.get("content_type") or "",
                            base=csv_path.parent,
                        )
                    )
                except RuntimeError as exc:
                    raise RuntimeError(f"Asset CSV row {line_number}: {exc}") from exc

    for path_value in _split_env_paths(os.environ.get("LOADTEST_IMAGE_PATHS", "")):
        assets.append(_asset_from_values("image", path_value))
    for path_value in _split_env_paths(os.environ.get("LOADTEST_VIDEO_PATHS", "")):
        assets.append(_asset_from_values("video", path_value))

    deduplicated: dict[tuple[str, Path], Asset] = {}
    for asset in assets:
        deduplicated[(asset.kind, asset.path)] = asset
    images = [asset for asset in deduplicated.values() if asset.kind == "image"]
    videos = [asset for asset in deduplicated.values() if asset.kind == "video"]
    return images, videos


ACCOUNTS = _load_accounts()
IMAGE_ASSETS, VIDEO_ASSETS = _load_assets()
ALLOW_ACCOUNT_REUSE = _env_bool("LOADTEST_ALLOW_ACCOUNT_REUSE", False)


class AccountPool:
    def __init__(self, accounts: list[Account], allow_reuse: bool):
        self._all = list(accounts)
        self._available = deque(accounts)
        self._reserved: set[str] = set()
        self._next_reused = 0
        self._allow_reuse = allow_reuse
        self._lock = threading.Lock()

    def acquire(self) -> Account | None:
        with self._lock:
            if self._available:
                account = self._available.popleft()
                self._reserved.add(account.username)
                return account
            if self._allow_reuse and self._all:
                account = self._all[self._next_reused % len(self._all)]
                self._next_reused += 1
                return account
            return None

    def release(self, account: Account | None) -> None:
        if account is None or self._allow_reuse:
            return
        with self._lock:
            if account.username in self._reserved:
                self._reserved.remove(account.username)
                self._available.append(account)


ACCOUNT_POOL = AccountPool(ACCOUNTS, ALLOW_ACCOUNT_REUSE)
CLASSIFICATIONS: Counter[str] = Counter()
CLASSIFICATION_LOCK = threading.Lock()
SHA256_CACHE: dict[Path, str] = {}
SHA256_LOCK = threading.Lock()


def _count_classification(name: str) -> None:
    with CLASSIFICATION_LOCK:
        CLASSIFICATIONS[name] += 1


def _rename_response(response, suffix: str) -> None:
    request_meta = getattr(response, "request_meta", None)
    if not request_meta:
        return
    base_name = request_meta.get("name") or request_meta.get("url") or "request"
    request_meta["name"] = f"{base_name} [{suffix}]"


def _response_excerpt(response, limit: int = 300) -> str:
    try:
        value = response.text.replace("\n", " ").strip()
    except Exception:  # pragma: no cover - defensive around streamed responses
        value = ""
    return value[:limit]


def _json_payload(response):
    try:
        return response.json()
    except (ValueError, TypeError):
        return None


def _has_business_key(*keys: str) -> Callable[[object], bool]:
    allowed = set(keys)

    def predicate(response) -> bool:
        payload = _json_payload(response)
        return isinstance(payload, dict) and bool(set(payload).intersection(allowed))

    return predicate


def _detail_contains(*phrases: str) -> Callable[[object], bool]:
    """Match only explicitly accepted business outcomes, never every HTTP 400."""

    def predicate(response) -> bool:
        payload = _json_payload(response)
        detail = payload.get("detail", "") if isinstance(payload, dict) else ""
        return isinstance(detail, str) and any(phrase in detail for phrase in phrases)

    return predicate


def _mark_malformed(response, classification: str, message: str) -> None:
    _rename_response(response, classification.replace("_", "-"))
    _count_classification(classification)
    response.failure(message)


def _classify(
    response,
    *,
    ok_statuses: tuple[int, ...] = (200,),
    expected_400: bool | Callable[[object], bool] = False,
) -> str:
    """Classify a response without ever accepting a server-side error."""

    status_code = response.status_code
    if status_code >= 500:
        _rename_response(response, f"server-{status_code}")
        _count_classification("server_error")
        response.failure(f"HTTP {status_code}: {_response_excerpt(response)}")
        return "server_error"

    if status_code in ok_statuses:
        _count_classification("ok")
        response.success()
        return "ok"

    if status_code == 429:
        _rename_response(response, "throttle-429")
        _count_classification("throttle_429")
        if ACCEPT_429:
            response.success()
        else:
            response.failure(f"HTTP 429 throttled: {_response_excerpt(response)}")
        return "throttle_429"

    is_expected_400 = status_code == 400 and (
        expected_400(response) if callable(expected_400) else expected_400
    )
    if is_expected_400:
        _rename_response(response, "business-400")
        _count_classification("business_400")
        response.success()
        return "business_400"

    _rename_response(response, f"unexpected-{status_code}")
    _count_classification("unexpected_error")
    response.failure(f"unexpected HTTP {status_code}: {_response_excerpt(response)}")
    return "unexpected_error"


def _sha256(path: Path) -> str:
    with SHA256_LOCK:
        cached = SHA256_CACHE.get(path)
    if cached:
        return cached
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(4 * MIB):
            digest.update(block)
    value = digest.hexdigest()
    with SHA256_LOCK:
        SHA256_CACHE[path] = value
    return value


def _jwt_expiry(access_token: str) -> float:
    try:
        payload_part = access_token.split(".")[1]
        payload_part += "=" * (-len(payload_part) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_part.encode("ascii")))
        return float(payload["exp"])
    except (IndexError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return time.time() + 12 * 60


def _works_from_payload(payload) -> list[dict] | None:
    if not isinstance(payload, dict):
        return None
    required = {'count', 'page', 'page_size', 'total_pages', 'next', 'previous', 'results'}
    if not required.issubset(payload):
        return None
    count = payload['count']
    page = payload['page']
    page_size = payload['page_size']
    total_pages = payload['total_pages']
    results = payload['results']
    if not all(type(value) is int for value in (count, page, page_size, total_pages)):
        return None
    if count < 0 or page < 1 or page_size < 1 or total_pages < 1 or page > total_pages:
        return None
    if not isinstance(results, list) or any(not isinstance(item, dict) for item in results):
        return None
    if len(results) > page_size or count < len(results):
        return None
    if not all(payload[key] is None or isinstance(payload[key], str) for key in ('next', 'previous')):
        return None
    return results


def _is_test_hostname(hostname: str) -> bool:
    normalized = hostname.strip().lower()
    if normalized in {'localhost', '127.0.0.1', '::1'}:
        return True
    accepted_labels = {'test', 'loadtest', 'staging', 'stage', 'qa', 'preprod'}
    return any(
        label in accepted_labels or label.startswith('loadtest-')
        for label in normalized.split('.')
    )


WRITE_TARGET_VERIFIED = False


def _requires_target_identity(environment) -> bool:
    user_classes = getattr(environment, "user_classes", ()) or ()
    authenticated_classes = {"AuthenticatedMixedUser", "UploadUser"}
    return (
        REQUIRE_TARGET_IDENTITY
        or ENABLE_INTERACTIONS
        or ENABLE_UPLOADS
        or any(getattr(user_class, "__name__", "") in authenticated_classes for user_class in user_classes)
    )


def _require_verified_write_target() -> None:
    if not WRITE_TARGET_VERIFIED:
        raise RuntimeError("Refusing write because the load-test backend identity was not verified")


@events.test_start.add_listener
def _on_test_start(environment, **kwargs):
    global WRITE_TARGET_VERIFIED
    WRITE_TARGET_VERIFIED = False
    target_host = (environment.host or "").strip().lower()
    target_hostname = (urlsplit(target_host).hostname or "").lower()
    mutating_test = _requires_target_identity(environment)
    if mutating_test and not _is_test_hostname(target_hostname):
        message = (
            "Refusing mutating load test against a non-test host. "
            "Use a localhost/loadtest/staging/test target; there is no production-write bypass."
        )
        LOGGER.critical(message)
        if environment.runner is not None:
            environment.runner.quit()
        raise RuntimeError(message)
    if mutating_test:
        try:
            fetch_and_validate_identity(
                target_host,
                EXPECTED_TARGET_ID,
                api_prefix=API_PREFIX,
            )
        except IdentityVerificationError as exc:
            message = f"Refusing load-test writes: {exc}"
            LOGGER.critical(message)
            if environment.runner is not None:
                environment.runner.quit()
            raise RuntimeError(message) from exc
        WRITE_TARGET_VERIFIED = True
    if not mutating_test and not _is_test_hostname(target_hostname):
        if NONTEST_READ_ACKNOWLEDGEMENT != "READ_ONLY":
            message = (
                "Refusing load traffic against a non-test host without the explicit "
                "LOADTEST_ALLOW_NONTEST_READS=READ_ONLY acknowledgement."
            )
            LOGGER.critical(message)
            if environment.runner is not None:
                environment.runner.quit()
            raise RuntimeError(message)
    LOGGER.info(
        "Load test configuration: accounts=%d images=%d videos=%d writes=%s "
        "interactions=%s uploads=%s accept_429=%s run_id=%s",
        len(ACCOUNTS),
        len(IMAGE_ASSETS),
        len(VIDEO_ASSETS),
        WRITES_CONFIRMED,
        ENABLE_INTERACTIONS,
        ENABLE_UPLOADS,
        ACCEPT_429,
        RUN_ID,
    )
    if not ACCOUNTS:
        LOGGER.warning("No credentials configured; only PublicBrowsingUser can run")
    if not WRITES_CONFIRMED:
        LOGGER.warning("Mutating scenarios are disabled; set LOADTEST_CONFIRM_WRITES=YES explicitly")
    if ENABLE_UPLOADS and not (IMAGE_ASSETS or VIDEO_ASSETS):
        LOGGER.warning("Upload scenarios were enabled but no valid image/video assets were configured")


@events.test_stop.add_listener
def _on_test_stop(environment, **kwargs):
    global WRITE_TARGET_VERIFIED
    WRITE_TARGET_VERIFIED = False
    with CLASSIFICATION_LOCK:
        summary = dict(sorted(CLASSIFICATIONS.items()))
    LOGGER.info("HTTP outcome classifications: %s", json.dumps(summary, ensure_ascii=False, sort_keys=True))


class GalleryUserBase(HttpUser):
    abstract = True
    wait_time = between(WAIT_MIN, WAIT_MAX)

    def _get_works(self, *, headers: dict[str, str] | None = None, name: str = "GET /api/works") -> list[dict]:
        with self.client.get(
            _api("works/?page=1&page_size=8"),
            headers=headers,
            name=name,
            catch_response=True,
        ) as response:
            outcome = _classify(response)
            if outcome != "ok":
                return []
            works = _works_from_payload(_json_payload(response))
            if works is None:
                _mark_malformed(
                    response,
                    "invalid_work_page",
                    "work list response did not match the paginated API contract",
                )
                return []
            if not works:
                _count_classification("empty_work_list")
            return works

    def _same_origin_target(self, raw_url: str) -> str | None:
        if not raw_url:
            return None
        parsed = urlsplit(raw_url)
        if not parsed.scheme and not parsed.netloc:
            return raw_url if raw_url.startswith("/") else f"/{raw_url}"
        configured_host = self.environment.host or getattr(self, "host", "") or ""
        configured_netloc = urlsplit(configured_host).netloc
        if configured_netloc and parsed.netloc != configured_netloc:
            return None
        target = parsed.path or "/"
        if parsed.query:
            target += f"?{parsed.query}"
        return target

    @staticmethod
    def _media_candidates(works: list[dict]) -> list[tuple[str, str]]:
        candidates: list[tuple[str, str]] = []
        for work in works:
            media_type = str(work.get("media_type") or "")
            attachment = work.get("attachment")
            if isinstance(attachment, str) and attachment:
                candidates.append((attachment, "video" if media_type == "video" else "attachment"))
            image = work.get("image")
            if isinstance(image, str) and image:
                candidates.append((image, "image"))
            image_url = work.get("image_url")
            if isinstance(image_url, str) and image_url:
                candidates.append((image_url, "image"))
            for gallery_image in work.get("images") or []:
                if isinstance(gallery_image, dict) and isinstance(gallery_image.get("image"), str):
                    candidates.append((gallery_image["image"], "image"))
        return candidates

    def _download_media(self, raw_url: str, media_kind: str, *, headers: dict[str, str] | None = None) -> None:
        target = self._same_origin_target(raw_url)
        if not target:
            _count_classification("external_media_skipped")
            return

        request_headers = dict(headers or {})
        ok_statuses = (200,)
        request_name = "GET /media/work-file"
        if media_kind == "video":
            request_headers["Range"] = f"bytes=0-{MEDIA_RANGE_BYTES - 1}"
            ok_statuses = (206,)
            request_name = "GET /media/work-video [Range]"
        elif media_kind == "image":
            request_name = "GET /media/work-image"

        started = time.perf_counter()
        with self.client.get(
            target,
            headers=request_headers,
            name=request_name,
            catch_response=True,
            stream=True,
        ) as response:
            total_read = 0
            read_limit = MEDIA_RANGE_BYTES if media_kind == "video" else MEDIA_READ_LIMIT
            if response.status_code < 500:
                for block in response.iter_content(chunk_size=64 * 1024):
                    if not block:
                        continue
                    total_read += len(block)
                    if read_limit and total_read >= read_limit:
                        break
            response.close()
            request_meta = getattr(response, "request_meta", None)
            if request_meta is not None:
                request_meta["response_time"] = (time.perf_counter() - started) * 1000
                request_meta["response_length"] = total_read
            if media_kind == "video" and response.status_code == 200:
                _count_classification("range_ignored")
            outcome = _classify(response, ok_statuses=ok_statuses)
            if outcome != "ok":
                return
            if total_read <= 0:
                _mark_malformed(response, "empty_media_response", "media response contained no bytes")
                return
            if media_kind == "video":
                content_range = response.headers.get("Content-Range", "")
                if not content_range.startswith("bytes "):
                    _mark_malformed(
                        response,
                        "invalid_content_range",
                        "video Range response did not include a valid Content-Range header",
                    )


class PublicBrowsingUser(GalleryUserBase):
    """Anonymous traffic: landing page, works, camp, tags and leaderboard."""

    abstract = False
    weight = PUBLIC_USER_WEIGHT

    def browse_landing(self) -> None:
        with self.client.get("/", name="GET /", catch_response=True) as response:
            _classify(response)

    def browse_public_feed(self) -> None:
        works = self._get_works(name="GET /api/works [public]")
        if works and random.random() < 0.5:
            work_id = random.choice(works).get("id")
            if work_id:
                with self.client.get(
                    _api(f"works/{work_id}/"),
                    name="GET /api/works/:id [public]",
                    catch_response=True,
                ) as response:
                    _classify(response)

    def browse_public_discovery(self) -> None:
        path, name = random.choice(
            [
                ("camps/current/", "GET /api/camps/current"),
                ("leaderboard/", "GET /api/leaderboard"),
                ("tags/popular/", "GET /api/tags/popular"),
            ]
        )
        with self.client.get(_api(path), name=name, catch_response=True) as response:
            _classify(response)

    def browse_public_media(self) -> None:
        works = self._get_works(name="GET /api/works [media-catalog]")
        candidates = self._media_candidates(works)
        if candidates:
            self._download_media(*random.choice(candidates))

    tasks = {
        browse_landing: max(1, BROWSE_TASK_WEIGHT // 3),
        browse_public_feed: BROWSE_TASK_WEIGHT,
        browse_public_discovery: max(1, BROWSE_TASK_WEIGHT // 2),
        browse_public_media: MEDIA_TASK_WEIGHT,
    }


class AuthenticatedUserBase(GalleryUserBase):
    abstract = True
    account: Account | None = None
    access_token = ""
    refresh_token = ""
    access_expires_at = 0.0

    def on_start(self) -> None:
        self.account = ACCOUNT_POOL.acquire()
        self.created_work_ids: list[int] = []
        self.cached_works: list[dict] = []
        self.image_upload_attempts = 0
        self.video_upload_attempts = 0
        self.liked_work_ids: set[int] = set()
        self.voted_work_ids: set[int] = set()
        self.vote_limit_reached = False
        if self.account is None:
            LOGGER.error(
                "Not enough unique test accounts. Add rows to LOADTEST_ACCOUNTS_CSV or explicitly set "
                "LOADTEST_ALLOW_ACCOUNT_REUSE=1."
            )
            raise StopUser()
        if not self._login():
            raise StopUser()

    def on_stop(self) -> None:
        if CLEANUP_CREATED and self.created_work_ids and self.access_token:
            _require_verified_write_target()
            for work_id in reversed(self.created_work_ids):
                try:
                    headers = {"Authorization": f"Bearer {self.access_token}"}
                    with self.client.delete(
                        _api(f"works/{work_id}/"),
                        headers=headers,
                        name="DELETE /api/works/:id [cleanup]",
                        catch_response=True,
                    ) as response:
                        _classify(response, ok_statuses=(204, 404))
                except Exception:
                    LOGGER.exception("Could not clean up a load-test work")
        ACCOUNT_POOL.release(self.account)

    def _login(self) -> bool:
        _require_verified_write_target()
        assert self.account is not None
        with self.client.post(
            _api("auth/token/"),
            json={"username": self.account.username, "password": self.account.password},
            name="POST /api/auth/token",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                payload = _json_payload(response)
                if not isinstance(payload, dict) or not payload.get("access") or not payload.get("refresh"):
                    _count_classification("malformed_login_response")
                    response.failure("login response did not contain access and refresh tokens")
                    return False
                self._store_tokens(payload)
                _classify(response)
                return True
            _classify(response)
            return False

    def _store_tokens(self, payload: dict) -> None:
        self.access_token = str(payload["access"])
        if payload.get("refresh"):
            self.refresh_token = str(payload["refresh"])
        self.access_expires_at = _jwt_expiry(self.access_token)

    def _refresh_access(self) -> bool:
        _require_verified_write_target()
        if not self.refresh_token:
            return False
        with self.client.post(
            _api("auth/token/refresh/"),
            json={"refresh": self.refresh_token},
            name="POST /api/auth/token/refresh",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                payload = _json_payload(response)
                if not isinstance(payload, dict) or not payload.get("access"):
                    _count_classification("malformed_refresh_response")
                    response.failure("refresh response did not contain an access token")
                    return False
                self._store_tokens(payload)
                _classify(response)
                return True
            _classify(response)
            return False

    def _auth_headers(self) -> dict[str, str]:
        if self.access_expires_at <= time.time() + 45 and not self._refresh_access():
            raise StopUser()
        return {"Authorization": f"Bearer {self.access_token}"}

    def _authenticated_works(self, *, refresh: bool = False) -> list[dict]:
        if self.cached_works and not refresh:
            return self.cached_works
        self.cached_works = self._get_works(
            headers=self._auth_headers(),
            name="GET /api/works [authenticated]",
        )
        return self.cached_works

    def _unique_title(self, media_kind: str) -> str:
        username = self.account.username if self.account else "user"
        safe_username = re.sub(r"[^A-Za-z0-9_-]+", "-", username)[:24] or "user"
        return f"loadtest-{RUN_ID}-{media_kind}-{safe_username}-{uuid.uuid4().hex[:8]}"[:120]


class AuthenticatedMixedUser(AuthenticatedUserBase):
    """Signed-in browsing, searching, media reads, likes and votes."""

    abstract = not bool(ACCOUNTS)
    weight = AUTH_USER_WEIGHT

    def browse_account_and_courses(self) -> None:
        path, name = random.choice(
            [
                ("me/", "GET /api/me"),
                ("courses/", "GET /api/courses"),
                ("works/my/", "GET /api/works/my"),
            ]
        )
        with self.client.get(
            _api(path),
            headers=self._auth_headers(),
            name=name,
            catch_response=True,
        ) as response:
            _classify(response)

    def browse_feed_and_detail(self) -> None:
        works = self._authenticated_works(refresh=True)
        if not works:
            return
        work_id = random.choice(works).get("id")
        if work_id:
            with self.client.get(
                _api(f"works/{work_id}/"),
                headers=self._auth_headers(),
                name="GET /api/works/:id [authenticated]",
                catch_response=True,
            ) as response:
                _classify(response)

    def search(self) -> None:
        with self.client.get(
            _api("search/"),
            params={"q": SEARCH_TERM},
            headers=self._auth_headers(),
            name="GET /api/search",
            catch_response=True,
        ) as response:
            _classify(response)

    def browse_authenticated_media(self) -> None:
        works = self._authenticated_works()
        candidates = self._media_candidates(works)
        html_works = [work for work in works if work.get("media_type") == "html" and work.get("has_attachment")]
        if html_works and random.random() < 0.2:
            work_id = random.choice(html_works).get("id")
            if work_id:
                self._download_media(
                    _api(f"works/{work_id}/file/"),
                    "attachment",
                    headers=self._auth_headers(),
                )
                return
        if candidates:
            self._download_media(*random.choice(candidates), headers=self._auth_headers())

    def like_or_vote(self) -> None:
        if not ENABLE_INTERACTIONS:
            self.browse_feed_and_detail()
            return
        works = self._authenticated_works(refresh=True)
        if not works:
            return

        actions = ["like"]
        if not self.vote_limit_reached:
            actions.append("vote")
        random.shuffle(actions)
        action = ""
        work_id = 0
        for candidate_action in actions:
            seen = self.liked_work_ids if candidate_action == "like" else self.voted_work_ids
            candidates = [
                work.get("id")
                for work in works
                if isinstance(work.get("id"), int) and work["id"] not in seen
            ]
            if candidates:
                action = candidate_action
                work_id = random.choice(candidates)
                break
        if not action or not work_id:
            self.browse_feed_and_detail()
            return

        _require_verified_write_target()
        accepted_business_outcome = (
            _detail_contains("已经点赞过这个作品")
            if action == "like"
            else _detail_contains("已经给这个作品投过票", "最多只能投")
        )
        with self.client.post(
            _api(f"works/{work_id}/{action}/"),
            json={},
            headers=self._auth_headers(),
            name=f"POST /api/works/:id/{action}",
            catch_response=True,
        ) as response:
            outcome = _classify(
                response,
                ok_statuses=(201,),
                expected_400=accepted_business_outcome,
            )
            if outcome not in {"ok", "business_400"}:
                return
            if action == "like":
                self.liked_work_ids.add(work_id)
            else:
                self.voted_work_ids.add(work_id)
                payload = _json_payload(response)
                detail = payload.get("detail", "") if isinstance(payload, dict) else ""
                if "最多只能投" in str(detail):
                    self.vote_limit_reached = True

    tasks = {
        browse_account_and_courses: BROWSE_TASK_WEIGHT,
        browse_feed_and_detail: BROWSE_TASK_WEIGHT,
        search: SEARCH_TASK_WEIGHT,
        browse_authenticated_media: MEDIA_TASK_WEIGHT,
        like_or_vote: INTERACTION_TASK_WEIGHT,
    }


class UploadUser(AuthenticatedUserBase):
    """Real multipart image uploads and real 8 MiB chunked video uploads."""

    abstract = not (ACCOUNTS and ENABLE_UPLOADS and (IMAGE_ASSETS or VIDEO_ASSETS))
    weight = UPLOAD_USER_WEIGHT

    def upload_images(self) -> None:
        if not IMAGE_ASSETS or self.image_upload_attempts >= MAX_IMAGE_UPLOADS:
            self._authenticated_works(refresh=True)
            return
        self.image_upload_attempts += 1
        _require_verified_write_target()
        count = min(IMAGES_PER_WORK, len(IMAGE_ASSETS), 10)
        selected = random.sample(IMAGE_ASSETS, count)
        data = {
            "title": self._unique_title("images"),
            "work_type": random.choice(("ai", "training")),
            "description": f"Automated load-test image upload ({RUN_ID}).",
            "link": "",
            "tags": json.dumps(["loadtest", RUN_ID[:16]]),
        }
        with ExitStack() as stack:
            files = [
                (
                    "images",
                    (
                        asset.path.name,
                        stack.enter_context(asset.path.open("rb")),
                        asset.content_type,
                    ),
                )
                for asset in selected
            ]
            with self.client.post(
                _api("works/"),
                data=data,
                files=files,
                headers=self._auth_headers(),
                name="POST /api/works [multipart-images]",
                catch_response=True,
            ) as response:
                outcome = _classify(
                    response,
                    ok_statuses=(201,),
                )
                if outcome == "ok":
                    payload = _json_payload(response)
                    images = payload.get("images") if isinstance(payload, dict) else None
                    if (
                        not isinstance(payload, dict)
                        or not isinstance(payload.get("id"), int)
                        or not isinstance(images, list)
                        or len(images) != count
                        or any(not isinstance(item, dict) or not item.get("image") for item in images)
                    ):
                        _mark_malformed(
                            response,
                            "malformed_image_create_response",
                            "image work response did not contain the work id and every uploaded image",
                        )
                        return
                    self.created_work_ids.append(payload["id"])

    def upload_video(self) -> None:
        if not VIDEO_ASSETS or self.video_upload_attempts >= MAX_VIDEO_UPLOADS:
            self._authenticated_works(refresh=True)
            return
        self.video_upload_attempts += 1
        _require_verified_write_target()
        asset = random.choice(VIDEO_ASSETS)
        total_size = asset.path.stat().st_size
        total_chunks = max(1, (total_size + VIDEO_CHUNK_BYTES - 1) // VIDEO_CHUNK_BYTES)
        init_payload = {
            "file_name": asset.path.name,
            "content_type": asset.content_type,
            "total_size": total_size,
            "total_chunks": total_chunks,
            "sha256": _sha256(asset.path),
        }
        with self.client.post(
            _api("uploads/init/"),
            json=init_payload,
            headers=self._auth_headers(),
            name="POST /api/uploads/init [video]",
            catch_response=True,
        ) as response:
            outcome = _classify(
                response,
                ok_statuses=(201,),
            )
            payload = _json_payload(response) if outcome == "ok" else None
            upload_id = payload.get("upload_id") if isinstance(payload, dict) else None
            if outcome != "ok":
                return
            if (
                not upload_id
                or payload.get("total_size") != total_size
                or payload.get("total_chunks") != total_chunks
            ):
                _mark_malformed(
                    response,
                    "malformed_upload_init_response",
                    "upload init response did not match the declared file metadata",
                )
                return

        with asset.path.open("rb") as source:
            for index in range(total_chunks):
                chunk = source.read(VIDEO_CHUNK_BYTES)
                if not chunk:
                    _count_classification("local_asset_short_read")
                    LOGGER.error("Video asset ended before declared chunk count: %s", asset.path)
                    return
                with self.client.post(
                    _api(f"uploads/{upload_id}/chunk/"),
                    data={"index": str(index)},
                    files={
                        "chunk": (
                            f"{asset.path.name}.part{index}",
                            chunk,
                            "application/octet-stream",
                        )
                    },
                    headers=self._auth_headers(),
                    name="POST /api/uploads/:id/chunk [8MiB]",
                    catch_response=True,
                ) as response:
                    if _classify(response) != "ok":
                        return
                    payload = _json_payload(response)
                    if (
                        not isinstance(payload, dict)
                        or payload.get("upload_id") != str(upload_id)
                        or payload.get("received") != index + 1
                        or payload.get("total_chunks") != total_chunks
                    ):
                        _mark_malformed(
                            response,
                            "malformed_chunk_response",
                            "chunk response did not confirm the expected received chunk count",
                        )
                        return

        with self.client.post(
            _api(f"uploads/{upload_id}/complete/"),
            headers=self._auth_headers(),
            name="POST /api/uploads/:id/complete [video]",
            catch_response=True,
        ) as response:
            if _classify(response) != "ok":
                return
            payload = _json_payload(response)
            if (
                not isinstance(payload, dict)
                or payload.get("upload_id") != str(upload_id)
                or payload.get("sha256") != init_payload["sha256"]
                or payload.get("total_size") != total_size
            ):
                _mark_malformed(
                    response,
                    "malformed_upload_complete_response",
                    "completed upload metadata or SHA-256 did not match the local file",
                )
                return

        work_data = {
            "title": self._unique_title("video"),
            "work_type": random.choice(("ai", "training")),
            "description": f"Automated load-test chunked video upload ({RUN_ID}).",
            "link": "",
            "tags": json.dumps(["loadtest", RUN_ID[:16]]),
            "upload_id": str(upload_id),
        }
        with self.client.post(
            _api("works/"),
            data=work_data,
            headers=self._auth_headers(),
            name="POST /api/works [create-video]",
            catch_response=True,
        ) as response:
            outcome = _classify(
                response,
                ok_statuses=(201,),
            )
            if outcome == "ok":
                payload = _json_payload(response)
                if (
                    not isinstance(payload, dict)
                    or not isinstance(payload.get("id"), int)
                    or payload.get("media_type") != "video"
                    or not payload.get("has_attachment")
                ):
                    _mark_malformed(
                        response,
                        "malformed_video_create_response",
                        "video work response did not contain a usable video attachment",
                    )
                    return
                self.created_work_ids.append(payload["id"])

    tasks: dict[Callable, int] = {}
    if IMAGE_ASSETS:
        tasks[upload_images] = IMAGE_UPLOAD_TASK_WEIGHT
    if VIDEO_ASSETS:
        tasks[upload_video] = VIDEO_UPLOAD_TASK_WEIGHT
