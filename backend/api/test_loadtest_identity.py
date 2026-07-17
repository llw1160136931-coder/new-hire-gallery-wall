from datetime import date

from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from .models import TrainingCamp


class LoadTestIdentityEndpointTests(APITestCase):
    def setUp(self):
        self.camp = TrainingCamp.objects.create(
            name='Load test camp',
            slug='loadtest_camp',
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            is_active=True,
        )

    @override_settings(LOADTEST_MODE=False, LOADTEST_TARGET_ID='must-not-leak')
    def test_disabled_backend_does_not_expose_configured_target_id(self):
        response = self.client.get('/api/loadtest/identity/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), {
            'schema_version': 1,
            'loadtest_mode': False,
            'target_id': None,
            'active_camp_slug': 'loadtest_camp',
        })
        self.assertEqual(response['Cache-Control'], 'no-store, max-age=0')

    @override_settings(LOADTEST_MODE=True, LOADTEST_TARGET_ID='lt-target-2026')
    def test_enabled_backend_returns_only_non_secret_identity_fields(self):
        response = self.client.get('/api/loadtest/identity/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(set(response.json()), {
            'schema_version', 'loadtest_mode', 'target_id', 'active_camp_slug',
        })
        self.assertEqual(response.json()['target_id'], 'lt-target-2026')
        self.assertTrue(response.json()['loadtest_mode'])

    @override_settings(LOADTEST_MODE=True, LOADTEST_TARGET_ID='lt-target-2026')
    def test_endpoint_reports_wrong_active_camp_instead_of_claiming_safety(self):
        self.camp.slug = 'ordinary_camp'
        self.camp.save(update_fields=['slug'])
        response = self.client.get('/api/loadtest/identity/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['active_camp_slug'], 'ordinary_camp')

    def test_endpoint_is_read_only(self):
        response = self.client.post('/api/loadtest/identity/', {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
