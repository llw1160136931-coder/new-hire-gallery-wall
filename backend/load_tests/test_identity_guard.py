import json
import threading
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from backend.load_tests.identity_guard import (
    IdentityVerificationError,
    fetch_and_validate_identity,
    identity_url,
)


GOOD_IDENTITY = {
    'schema_version': 1,
    'loadtest_mode': True,
    'target_id': 'lt-target-2026',
    'active_camp_slug': 'loadtest_camp',
}


@contextmanager
def identity_server(*, payload=None, content_type='application/json', redirect=False):
    body = json.dumps(payload if payload is not None else GOOD_IDENTITY).encode('utf-8')

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if redirect and self.path == '/api/loadtest/identity/':
                self.send_response(302)
                self.send_header('Location', '/forwarded/identity/')
                self.end_headers()
                return
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}'
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class IdentityGuardTests(unittest.TestCase):
    def test_valid_identity_is_accepted(self):
        with identity_server() as host:
            payload = fetch_and_validate_identity(host, 'lt-target-2026')
        self.assertEqual(payload, GOOD_IDENTITY)

    def test_wrong_target_or_camp_is_rejected(self):
        wrong_target = {**GOOD_IDENTITY, 'target_id': 'lt-other-2026'}
        with identity_server(payload=wrong_target) as host:
            with self.assertRaisesRegex(IdentityVerificationError, 'ID does not match'):
                fetch_and_validate_identity(host, 'lt-target-2026')

        wrong_camp = {**GOOD_IDENTITY, 'active_camp_slug': 'production_camp'}
        with identity_server(payload=wrong_camp) as host:
            with self.assertRaisesRegex(IdentityVerificationError, 'loadtest_camp'):
                fetch_and_validate_identity(host, 'lt-target-2026')

    def test_disabled_backend_is_rejected(self):
        payload = {**GOOD_IDENTITY, 'loadtest_mode': False, 'target_id': None}
        with identity_server(payload=payload) as host:
            with self.assertRaisesRegex(IdentityVerificationError, 'not in load-test mode'):
                fetch_and_validate_identity(host, 'lt-target-2026')

    def test_redirected_or_html_identity_is_rejected(self):
        with identity_server(redirect=True) as host:
            with self.assertRaisesRegex(IdentityVerificationError, 'redirects are not accepted'):
                fetch_and_validate_identity(host, 'lt-target-2026')
        with identity_server(content_type='text/html') as host:
            with self.assertRaisesRegex(IdentityVerificationError, 'application/json'):
                fetch_and_validate_identity(host, 'lt-target-2026')

    def test_identity_url_drops_paths_but_rejects_credentials_and_query(self):
        self.assertEqual(
            identity_url('https://loadtest.example.com/some/path'),
            'https://loadtest.example.com/api/loadtest/identity/',
        )
        with self.assertRaises(IdentityVerificationError):
            identity_url('https://user:password@loadtest.example.com')
        with self.assertRaises(IdentityVerificationError):
            identity_url('https://loadtest.example.com?target=other')


if __name__ == '__main__':
    unittest.main()
