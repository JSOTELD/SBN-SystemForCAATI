import unittest

from app import create_app


class OperationalHealthTest(unittest.TestCase):
    def test_health_reports_database_latency(self):
        app = create_app('testing')
        response = app.test_client().get('/api/health')
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload['status'], 'ok')
        self.assertIsInstance(payload['database_latency_ms'], (int, float))
        self.assertGreaterEqual(payload['database_latency_ms'], 0)


if __name__ == '__main__':
    unittest.main()
