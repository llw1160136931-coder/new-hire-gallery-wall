import argparse
import csv
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from backend.load_tests.run_suite import (
    READ_CONFIRMATION,
    SMOKE,
    UPLOAD_100,
    WRITE_CONFIRMATION,
    check_safety,
    count_credentials,
    is_test_host,
    main,
    phase_command,
    validate_assets,
)


class RunSuiteTests(unittest.TestCase):
    def test_dry_run_writes_suite_metadata_without_password(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            credentials = root / 'accounts.csv'
            with credentials.open('w', encoding='utf-8', newline='') as output:
                writer = csv.DictWriter(output, fieldnames=['username', 'password'])
                writer.writeheader()
                for index in range(5):
                    writer.writerow({
                        'username': f'loadtest_{index}',
                        'password': 'must-never-appear-in-output',
                    })
            for name in ('image.jpg', 'video.mp4'):
                (root / name).write_bytes(b'fixture')
            assets = root / 'assets.csv'
            with assets.open('w', encoding='utf-8', newline='') as output:
                writer = csv.DictWriter(output, fieldnames=['kind', 'path', 'content_type'])
                writer.writeheader()
                writer.writerow({'kind': 'image', 'path': 'image.jpg', 'content_type': 'image/jpeg'})
                writer.writerow({'kind': 'video', 'path': 'video.mp4', 'content_type': 'video/mp4'})
            captured = io.StringIO()
            with redirect_stdout(captured):
                exit_code = main([
                    '--host', 'http://127.0.0.1:8011',
                    '--credentials', str(credentials),
                    '--assets', str(assets),
                    '--preset', 'smoke',
                    '--confirm-writes', WRITE_CONFIRMATION,
                    '--target-id', 'lt-target-2026',
                    '--results-dir', str(root / 'results'),
                    '--dry-run',
                ])
            self.assertEqual(exit_code, 0)
            self.assertNotIn('must-never-appear-in-output', captured.getvalue())
            suite_files = list((root / 'results').glob('*/suite.json'))
            self.assertEqual(len(suite_files), 1)
            metadata = json.loads(suite_files[0].read_text(encoding='utf-8'))
            self.assertEqual(metadata['credential_count'], 5)
            self.assertNotIn('must-never-appear-in-output', json.dumps(metadata))

    def test_upload_100_preset_uses_100_real_upload_users(self):
        self.assertEqual(len(UPLOAD_100), 1)
        phase = UPLOAD_100[0]
        self.assertEqual(phase.users, 100)
        self.assertEqual(phase.classes, ('UploadUser',))
        self.assertTrue(phase.uploads)

    def test_test_host_detection_is_strict(self):
        self.assertTrue(is_test_host('http://127.0.0.1:8000'))
        self.assertTrue(is_test_host('https://loadtest.xinhuowall.com'))
        self.assertTrue(is_test_host('https://staging.example.com'))
        self.assertFalse(is_test_host('https://xinhuowall.com'))
        self.assertFalse(is_test_host('https://contest.example.com'))
        self.assertFalse(is_test_host('not-a-url'))

    def test_credentials_and_assets_are_validated_without_exposing_passwords(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            credentials = root / 'credentials.csv'
            with credentials.open('w', encoding='utf-8', newline='') as output:
                writer = csv.DictWriter(output, fieldnames=['username', 'password'])
                writer.writeheader()
                writer.writerow({'username': 'loadtest001', 'password': 'secret-not-logged'})
            image = root / 'image.jpg'
            video = root / 'video.mp4'
            image.write_bytes(b'image')
            video.write_bytes(b'video')
            assets = root / 'assets.csv'
            with assets.open('w', encoding='utf-8', newline='') as output:
                writer = csv.DictWriter(output, fieldnames=['kind', 'path', 'content_type'])
                writer.writeheader()
                writer.writerow({'kind': 'image', 'path': image.name, 'content_type': 'image/jpeg'})
                writer.writerow({'kind': 'video', 'path': video.name, 'content_type': 'video/mp4'})
            self.assertEqual(count_credentials(credentials), 1)
            self.assertIsNone(validate_assets(assets))

    def test_write_phases_are_never_allowed_on_production_host(self):
        args = argparse.Namespace(
            host='https://xinhuowall.com',
            duration_factor=1.0,
            confirm_writes=WRITE_CONFIRMATION,
            allow_production_read_only='',
            target_id='lt-target-2026',
        )
        with self.assertRaisesRegex(ValueError, 'never sends write load'):
            check_safety(args, list(SMOKE), credential_count=100)

    def test_test_host_requires_explicit_write_confirmation(self):
        args = argparse.Namespace(
            host='https://loadtest.xinhuowall.com',
            duration_factor=1.0,
            confirm_writes='',
            allow_production_read_only='',
            target_id='lt-target-2026',
        )
        with self.assertRaisesRegex(ValueError, '--confirm-writes'):
            check_safety(args, list(SMOKE), credential_count=100)
        args.confirm_writes = WRITE_CONFIRMATION
        self.assertIsNone(check_safety(args, list(SMOKE), credential_count=100))

    def test_non_test_read_only_requires_separate_confirmation(self):
        read_phase = [
            type(SMOKE[0])(
                'read-only', 1, 1, 1, ('PublicBrowsingUser',), public_weight=1
            )
        ]
        args = argparse.Namespace(
            host='https://xinhuowall.com',
            duration_factor=1.0,
            confirm_writes='',
            allow_production_read_only='',
        )
        with self.assertRaisesRegex(ValueError, '--allow-production-read-only'):
            check_safety(args, read_phase, credential_count=1)
        args.allow_production_read_only = READ_CONFIRMATION
        self.assertIsNone(check_safety(args, read_phase, credential_count=1))
        args.credentials = Path('accounts.csv')
        args.assets = Path('assets.csv')
        _, environment = phase_command(args, read_phase[0], Path('results'))
        self.assertEqual(environment['LOADTEST_ALLOW_NONTEST_READS'], READ_CONFIRMATION)

    def test_authenticated_phase_is_treated_as_write_due_to_login_side_effect(self):
        authenticated = type(SMOKE[0])(
            'auth-only', 1, 1, 1, ('AuthenticatedMixedUser',), auth_weight=1
        )
        self.assertTrue(authenticated.writes)
        args = argparse.Namespace(
            host='https://loadtest.xinhuowall.com',
            duration_factor=1.0,
            confirm_writes=WRITE_CONFIRMATION,
            allow_production_read_only='',
            target_id='',
        )
        with self.assertRaisesRegex(ValueError, '--target-id'):
            check_safety(args, [authenticated], credential_count=1)

    def test_write_phase_passes_expected_identity_to_locust(self):
        args = argparse.Namespace(
            host='https://loadtest.xinhuowall.com',
            credentials=Path('accounts.csv'),
            assets=Path('assets.csv'),
            duration_factor=1.0,
            target_id='lt-target-2026',
        )
        _, environment = phase_command(args, SMOKE[0], Path('results'))
        self.assertEqual(environment['LOADTEST_EXPECTED_TARGET_ID'], 'lt-target-2026')
        self.assertEqual(environment['LOADTEST_REQUIRE_TARGET_IDENTITY'], '1')

    def test_non_dry_run_preflights_identity_before_starting_locust(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            credentials = root / 'accounts.csv'
            with credentials.open('w', encoding='utf-8', newline='') as output:
                writer = csv.DictWriter(output, fieldnames=['username', 'password'])
                writer.writeheader()
                for index in range(5):
                    writer.writerow({'username': f'loadtest_{index}', 'password': 'test-password'})
            image = root / 'image.jpg'
            video = root / 'video.mp4'
            image.write_bytes(b'image')
            video.write_bytes(b'video')
            assets = root / 'assets.csv'
            with assets.open('w', encoding='utf-8', newline='') as output:
                writer = csv.DictWriter(output, fieldnames=['kind', 'path', 'content_type'])
                writer.writeheader()
                writer.writerow({'kind': 'image', 'path': image.name, 'content_type': 'image/jpeg'})
                writer.writerow({'kind': 'video', 'path': video.name, 'content_type': 'video/mp4'})

            with (
                mock.patch('backend.load_tests.run_suite.fetch_and_validate_identity') as verify,
                mock.patch('backend.load_tests.run_suite.subprocess.run') as run_process,
            ):
                run_process.return_value.returncode = 0
                exit_code = main([
                    '--host', 'https://loadtest.xinhuowall.com',
                    '--credentials', str(credentials),
                    '--assets', str(assets),
                    '--preset', 'smoke',
                    '--confirm-writes', WRITE_CONFIRMATION,
                    '--target-id', 'lt-target-2026',
                    '--results-dir', str(root / 'results'),
                ])

            self.assertEqual(exit_code, 0)
            verify.assert_called_once_with(
                'https://loadtest.xinhuowall.com', 'lt-target-2026', api_prefix='/api'
            )
            run_process.assert_called_once()
if __name__ == '__main__':
    unittest.main()
