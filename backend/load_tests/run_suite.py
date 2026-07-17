"""Run repeatable Locust load-test phases with production-write safeguards."""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

try:
    from backend.load_tests.identity_guard import (
        IdentityVerificationError,
        fetch_and_validate_identity,
        validate_target_id,
    )
except ModuleNotFoundError:
    from identity_guard import IdentityVerificationError, fetch_and_validate_identity, validate_target_id


ROOT = Path(__file__).resolve().parent
LOCUSTFILE = ROOT / 'locustfile.py'
WRITE_CONFIRMATION = 'LOADTEST_ONLY'
READ_CONFIRMATION = 'READ_ONLY'


@dataclass(frozen=True)
class Phase:
    name: str
    users: int
    spawn_rate: float
    duration_seconds: int
    classes: tuple[str, ...]
    public_weight: int = 0
    auth_weight: int = 0
    upload_weight: int = 0
    interactions: bool = False
    uploads: bool = False

    @property
    def writes(self) -> bool:
        # JWT login updates last_login, so authenticated "read" phases also
        # require the isolated-backend write guard.
        return self.interactions or self.uploads or any(
            name in {"AuthenticatedMixedUser", "UploadUser"} for name in self.classes
        )


SMOKE = (
    Phase(
        'smoke', 5, 1, 120,
        ('PublicBrowsingUser', 'AuthenticatedMixedUser', 'UploadUser'),
        public_weight=3, auth_weight=1, upload_weight=1,
        interactions=True, uploads=True,
    ),
)

TARGET_100 = SMOKE + (
    Phase(
        'browse-25', 25, 5, 300,
        ('PublicBrowsingUser', 'AuthenticatedMixedUser'),
        public_weight=3, auth_weight=2,
    ),
    Phase(
        'browse-50', 50, 10, 300,
        ('PublicBrowsingUser', 'AuthenticatedMixedUser'),
        public_weight=3, auth_weight=2,
    ),
    Phase(
        'browse-75', 75, 15, 300,
        ('PublicBrowsingUser', 'AuthenticatedMixedUser'),
        public_weight=3, auth_weight=2,
    ),
    Phase(
        'mixed-100', 100, 10, 1800,
        ('PublicBrowsingUser', 'AuthenticatedMixedUser', 'UploadUser'),
        public_weight=60, auth_weight=25, upload_weight=15,
        interactions=True, uploads=True,
    ),
    Phase(
        'upload-spike', 60, 10, 900,
        ('PublicBrowsingUser', 'UploadUser'),
        public_weight=50, upload_weight=10,
        uploads=True,
    ),
)

UPLOAD_100 = (
    Phase(
        'upload-100', 100, 10, 1800,
        ('UploadUser',),
        upload_weight=1,
        uploads=True,
    ),
)

FULL = TARGET_100 + UPLOAD_100 + (
    Phase(
        'login-spike-100', 100, 20, 600,
        ('AuthenticatedMixedUser',),
        auth_weight=1,
    ),
    Phase(
        'soak-100', 100, 10, 7200,
        ('PublicBrowsingUser', 'AuthenticatedMixedUser', 'UploadUser'),
        public_weight=70, auth_weight=25, upload_weight=5,
        interactions=True, uploads=True,
    ),
    Phase(
        'stress-125', 125, 10, 600,
        ('PublicBrowsingUser', 'AuthenticatedMixedUser', 'UploadUser'),
        public_weight=70, auth_weight=25, upload_weight=5,
        interactions=True, uploads=True,
    ),
    Phase(
        'stress-150', 150, 10, 600,
        ('PublicBrowsingUser', 'AuthenticatedMixedUser', 'UploadUser'),
        public_weight=70, auth_weight=25, upload_weight=5,
        interactions=True, uploads=True,
    ),
    Phase(
        'stress-200', 200, 10, 600,
        ('PublicBrowsingUser', 'AuthenticatedMixedUser', 'UploadUser'),
        public_weight=70, auth_weight=25, upload_weight=5,
        interactions=True, uploads=True,
    ),
)

PRESETS = {
    'smoke': SMOKE,
    'target100': TARGET_100,
    'upload100': UPLOAD_100,
    'full': FULL,
}


def is_test_host(raw_url: str) -> bool:
    parsed = urlparse(raw_url)
    hostname = (parsed.hostname or '').lower()
    if parsed.scheme not in {'http', 'https'} or not hostname:
        return False
    if hostname in {'localhost', '127.0.0.1', '::1'}:
        return True
    labels = hostname.split('.')
    accepted = {'test', 'loadtest', 'staging', 'stage', 'qa', 'preprod'}
    return any(label in accepted or label.startswith('loadtest-') for label in labels)


def count_credentials(path: Path) -> int:
    with path.open('r', encoding='utf-8-sig', newline='') as source:
        reader = csv.DictReader(source)
        headers = set(reader.fieldnames or [])
        if not {'username', 'password'}.issubset(headers):
            raise ValueError('credentials CSV must contain username,password columns')
        count = sum(
            1 for row in reader
            if str(row.get('username', '')).strip() and str(row.get('password', '')).strip()
        )
    if not count:
        raise ValueError('credentials CSV contains no usable accounts')
    return count


def validate_assets(path: Path) -> None:
    with path.open('r', encoding='utf-8-sig', newline='') as source:
        rows = list(csv.DictReader(source))
    if not rows:
        raise ValueError('assets CSV contains no fixtures')
    kinds: set[str] = set()
    for row in rows:
        kind = str(row.get('kind', '')).strip().lower()
        asset_path = Path(str(row.get('path', '')).strip()).expanduser()
        if not asset_path.is_absolute():
            asset_path = path.parent / asset_path
        asset_path = asset_path.resolve()
        content_type = str(row.get('content_type', '')).strip()
        if kind not in {'image', 'video'}:
            raise ValueError(f'unsupported asset kind: {kind!r}')
        if not asset_path.is_file():
            raise FileNotFoundError(f'asset does not exist: {asset_path}')
        if not content_type:
            raise ValueError(f'asset content_type is missing: {asset_path}')
        kinds.add(kind)
    if not {'image', 'video'}.issubset(kinds):
        raise ValueError('assets CSV must include at least one image and one video')


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True, help='Target base URL, for example https://loadtest.example.com')
    parser.add_argument('--credentials', type=Path, required=True, help='CSV generated by prepare_load_test.')
    parser.add_argument('--assets', type=Path, required=True, help='CSV generated by generate_fixtures.py.')
    parser.add_argument('--preset', choices=PRESETS, default='smoke')
    parser.add_argument('--phase', action='append', help='Run only named phases from the chosen preset.')
    parser.add_argument('--results-dir', type=Path, default=ROOT / 'results')
    parser.add_argument('--duration-factor', type=float, default=1.0, help='Scale phase durations; useful for rehearsals.')
    parser.add_argument('--confirm-writes', default='', help=f'Required literal for write phases: {WRITE_CONFIRMATION}')
    parser.add_argument(
        '--target-id', default='',
        help='Expected non-secret LOADTEST_TARGET_ID configured on the isolated backend.',
    )
    parser.add_argument(
        '--allow-production-read-only', default='',
        help=f'Required literal for read-only phases on a non-test hostname: {READ_CONFIRMATION}',
    )
    parser.add_argument('--continue-on-failure', action='store_true')
    parser.add_argument('--dry-run', action='store_true', help='Validate and print commands without sending traffic.')
    return parser


def select_phases(args: argparse.Namespace) -> list[Phase]:
    phases = list(PRESETS[args.preset])
    if args.phase:
        selected = set(args.phase)
        known = {phase.name for phase in phases}
        unknown = selected - known
        if unknown:
            raise ValueError(f'unknown phase(s) for {args.preset}: {", ".join(sorted(unknown))}')
        phases = [phase for phase in phases if phase.name in selected]
    if not phases:
        raise ValueError('no phases selected')
    return phases


def check_safety(args: argparse.Namespace, phases: list[Phase], credential_count: int) -> None:
    if args.duration_factor <= 0:
        raise ValueError('--duration-factor must be greater than zero')
    any_writes = any(phase.writes for phase in phases)
    if any_writes:
        try:
            validate_target_id(args.target_id)
        except IdentityVerificationError as exc:
            raise ValueError(f"write phases require a valid --target-id: {exc}") from exc
    if any_writes and args.confirm_writes != WRITE_CONFIRMATION:
        raise ValueError(
            f'write phases require --confirm-writes {WRITE_CONFIRMATION}; '
            'this confirms the target is an isolated load-test environment'
        )
    if not is_test_host(args.host):
        if any_writes:
            raise ValueError('run_suite.py never sends write load to a non-test hostname')
        if args.allow_production_read_only != READ_CONFIRMATION:
            raise ValueError(
                f'non-test read-only traffic requires --allow-production-read-only {READ_CONFIRMATION}'
            )
    required_accounts = max(
        (phase.users for phase in phases if 'PublicBrowsingUser' not in phase.classes or len(phase.classes) > 1),
        default=0,
    )
    if credential_count < required_accounts:
        raise ValueError(
            f'{required_accounts} accounts are required but only {credential_count} are available'
        )


def phase_command(
    args: argparse.Namespace,
    phase: Phase,
    output_dir: Path,
) -> tuple[list[str], dict[str, str]]:
    duration = max(1, round(phase.duration_seconds * args.duration_factor))
    prefix = output_dir / phase.name
    command = [
        sys.executable,
        '-m',
        'locust',
        '-f',
        str(LOCUSTFILE),
        '--headless',
        '--host',
        args.host.rstrip('/'),
        '--users',
        str(phase.users),
        '--spawn-rate',
        str(phase.spawn_rate),
        '--run-time',
        f'{duration}s',
        '--stop-timeout',
        '60',
        '--csv',
        str(prefix),
        '--csv-full-history',
        '--html',
        str(prefix.with_suffix('.html')),
        '--logfile',
        str(prefix.with_suffix('.log')),
        '--loglevel',
        'INFO',
        '--only-summary',
        *phase.classes,
    ]
    run_id = f'{output_dir.name}-{phase.name}'
    environment = {
        **os.environ,
        'LOADTEST_ACCOUNTS_CSV': str(args.credentials.resolve()),
        'LOADTEST_ASSETS_CSV': str(args.assets.resolve()),
        'LOADTEST_RUN_ID': run_id,
        'LOADTEST_CONFIRM_WRITES': 'YES' if phase.writes else '',
        'LOADTEST_ENABLE_INTERACTIONS': '1' if phase.interactions else '0',
        'LOADTEST_ENABLE_UPLOADS': '1' if phase.uploads else '0',
        'LOADTEST_CLEANUP_CREATED': '0',
        'LOADTEST_ACCEPT_429': '0',
        'LOADTEST_ALLOW_NONTEST_READS': (
            READ_CONFIRMATION if not is_test_host(args.host) and not phase.writes else ''
        ),
        'LOADTEST_EXPECTED_TARGET_ID': args.target_id if phase.writes else '',
        'LOADTEST_REQUIRE_TARGET_IDENTITY': '1' if phase.writes else '0',
        'LOADTEST_PUBLIC_USER_WEIGHT': str(phase.public_weight),
        'LOADTEST_AUTH_USER_WEIGHT': str(phase.auth_weight),
        'LOADTEST_UPLOAD_USER_WEIGHT': str(phase.upload_weight),
        'LOADTEST_MAX_IMAGE_UPLOADS_PER_USER': '1',
        'LOADTEST_MAX_VIDEO_UPLOADS_PER_USER': '1',
        'LOADTEST_IMAGES_PER_WORK': '3',
        'LOADTEST_API_PREFIX': '/api',
    }
    return command, environment


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if not LOCUSTFILE.is_file():
            raise FileNotFoundError(f'Locust file is missing: {LOCUSTFILE}')
        if not args.credentials.is_file():
            raise FileNotFoundError(f'credentials CSV is missing: {args.credentials}')
        if not args.assets.is_file():
            raise FileNotFoundError(f'assets CSV is missing: {args.assets}')
        credential_count = count_credentials(args.credentials)
        validate_assets(args.assets)
        phases = select_phases(args)
        check_safety(args, phases, credential_count)
        if not args.dry_run and any(phase.writes for phase in phases):
            fetch_and_validate_identity(args.host, args.target_id, api_prefix="/api")
    except (OSError, ValueError, IdentityVerificationError) as exc:
        print(f'suite validation failed: {exc}', file=sys.stderr)
        return 2

    timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    output_dir = args.results_dir / f'{timestamp}-{args.preset}'
    output_dir.mkdir(parents=True, exist_ok=False)
    metadata = {
        'schema_version': 1,
        'created_at': timestamp,
        'target': args.host,
        'preset': args.preset,
        'duration_factor': args.duration_factor,
        'credential_count': credential_count,
        'phases': [asdict(phase) for phase in phases],
        'results': [],
    }

    final_code = 0
    for phase in phases:
        command, environment = phase_command(args, phase, output_dir)
        safe_command = ' '.join(command)
        print(f'\n=== {phase.name}: {safe_command} ===', flush=True)
        if args.dry_run:
            result_code = 0
        else:
            result_code = subprocess.run(command, env=environment, check=False).returncode
        metadata['results'].append({'phase': phase.name, 'exit_code': result_code})
        (output_dir / 'suite.json').write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + '\n',
            encoding='utf-8',
        )
        if result_code:
            final_code = result_code
            print(f'{phase.name} failed with exit code {result_code}', file=sys.stderr)
            if not args.continue_on_failure:
                break

    print(f'\nSuite results: {output_dir.resolve()}')
    return final_code


if __name__ == '__main__':
    raise SystemExit(main())
