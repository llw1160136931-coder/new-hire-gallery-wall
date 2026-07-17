import unittest
from unittest import mock

from backend.load_tests import locustfile


class _JsonResponse:
    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


class _Runner:
    def __init__(self):
        self.quit_called = False

    def quit(self):
        self.quit_called = True


class _Environment:
    def __init__(self, host, user_classes=()):
        self.host = host
        self.runner = _Runner()
        self.user_classes = user_classes


class LocustFileSafetyTests(unittest.TestCase):
    def tearDown(self):
        locustfile.WRITE_TARGET_VERIFIED = False

    def test_test_hostname_detection_does_not_accept_substrings(self):
        self.assertTrue(locustfile._is_test_hostname('localhost'))
        self.assertTrue(locustfile._is_test_hostname('loadtest.xinhuowall.com'))
        self.assertTrue(locustfile._is_test_hostname('api.loadtest-east.example.com'))
        self.assertFalse(locustfile._is_test_hostname('xinhuowall.com'))
        self.assertFalse(locustfile._is_test_hostname('contest.example.com'))

    def test_direct_locust_write_is_rejected_on_production_host(self):
        environment = _Environment('https://xinhuowall.com')
        with (
            mock.patch.object(locustfile, 'ENABLE_INTERACTIONS', True),
            mock.patch.object(locustfile, 'ENABLE_UPLOADS', False),
        ):
            with self.assertRaisesRegex(RuntimeError, 'no production-write bypass'):
                locustfile._on_test_start(environment)
        self.assertTrue(environment.runner.quit_called)

    def test_direct_locust_write_is_allowed_on_explicit_test_host(self):
        environment = _Environment('https://loadtest.xinhuowall.com')
        with (
            mock.patch.object(locustfile, 'ENABLE_INTERACTIONS', True),
            mock.patch.object(locustfile, 'ENABLE_UPLOADS', False),
            mock.patch.object(locustfile, 'EXPECTED_TARGET_ID', 'lt-target-2026'),
            mock.patch.object(locustfile, 'fetch_and_validate_identity') as verify,
        ):
            locustfile._on_test_start(environment)
        verify.assert_called_once_with(
            'https://loadtest.xinhuowall.com',
            'lt-target-2026',
            api_prefix='/api',
        )
        self.assertFalse(environment.runner.quit_called)
        self.assertTrue(locustfile.WRITE_TARGET_VERIFIED)

    def test_wrong_backend_identity_stops_direct_locust_before_writes(self):
        environment = _Environment('https://loadtest.xinhuowall.com')
        with (
            mock.patch.object(locustfile, 'ENABLE_INTERACTIONS', True),
            mock.patch.object(locustfile, 'EXPECTED_TARGET_ID', 'lt-target-2026'),
            mock.patch.object(
                locustfile,
                'fetch_and_validate_identity',
                side_effect=locustfile.IdentityVerificationError('target backend ID does not match'),
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, 'target backend ID does not match'):
                locustfile._on_test_start(environment)
        self.assertTrue(environment.runner.quit_called)
        self.assertFalse(locustfile.WRITE_TARGET_VERIFIED)

    def test_authenticated_read_phase_also_requires_identity_before_login_write(self):
        authenticated_class = type('AuthenticatedMixedUser', (), {})
        environment = _Environment(
            'https://loadtest.xinhuowall.com',
            user_classes=(authenticated_class,),
        )
        with (
            mock.patch.object(locustfile, 'ENABLE_INTERACTIONS', False),
            mock.patch.object(locustfile, 'ENABLE_UPLOADS', False),
            mock.patch.object(locustfile, 'EXPECTED_TARGET_ID', ''),
            mock.patch.object(
                locustfile,
                'fetch_and_validate_identity',
                side_effect=locustfile.IdentityVerificationError('expected target ID is missing'),
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, 'expected target ID is missing'):
                locustfile._on_test_start(environment)
        self.assertTrue(environment.runner.quit_called)

    def test_write_guard_fails_closed_if_startup_verification_was_bypassed(self):
        locustfile.WRITE_TARGET_VERIFIED = False
        with self.assertRaisesRegex(RuntimeError, 'identity was not verified'):
            locustfile._require_verified_write_target()

    def test_direct_read_load_requires_acknowledgement_on_production(self):
        environment = _Environment('https://xinhuowall.com')
        with (
            mock.patch.object(locustfile, 'ENABLE_INTERACTIONS', False),
            mock.patch.object(locustfile, 'ENABLE_UPLOADS', False),
            mock.patch.object(locustfile, 'NONTEST_READ_ACKNOWLEDGEMENT', ''),
        ):
            with self.assertRaisesRegex(RuntimeError, 'LOADTEST_ALLOW_NONTEST_READS=READ_ONLY'):
                locustfile._on_test_start(environment)
        self.assertTrue(environment.runner.quit_called)

    def test_business_400_predicate_only_accepts_named_outcomes(self):
        predicate = locustfile._detail_contains('已经点赞过这个作品', '最多只能投')
        self.assertTrue(predicate(_JsonResponse({'detail': '你已经点赞过这个作品'})))
        self.assertFalse(predicate(_JsonResponse({'detail': '投稿时间已结束'})))
        self.assertFalse(predicate(_JsonResponse({'other': '已经点赞过这个作品'})))


if __name__ == '__main__':
    unittest.main()
