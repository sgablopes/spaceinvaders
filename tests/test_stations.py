import tempfile
import unittest
from pathlib import Path

from app import create_app


class StationTelemetryTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        app = create_app({'TESTING': True, 'STATION_DB_PATH': str(Path(self.directory.name) / 'stations.sqlite3'),
                          'STATION_KEYS': {'agrion-demo-001': 'test-secret'}})
        self.client = app.test_client()
        self.url = '/api/v1/stations/telemetry'
        self.body = {'station_id': 'agrion-demo-001', 'measurements': {'rain_detected': False,
                     'temperature_c': 26.5, 'humidity_pct': 72.3, 'vento_estimado_m_s': 3.2,
                     'yl38_d0': 1, 'lm393_nivel': 0, 'motor_adc_raw': 1520, 'wind_voltage_mv': 1250}}

    def tearDown(self):
        self.directory.cleanup()

    def send(self, body=None, key='test-secret'):
        return self.client.post(self.url, json=body or self.body, headers={'X-Station-Key': key})

    def test_receives_only_useful_fields_and_queries_latest_and_interval(self):
        self.assertEqual(self.send(key='wrong').status_code, 401)
        received = self.send()
        self.assertEqual(received.status_code, 201)
        latest = self.client.get('/api/v1/stations/agrion-demo-001/telemetry/latest')
        self.assertEqual(latest.status_code, 200)
        self.assertEqual(latest.json['reading']['measurements']['rain_detected'], False)
        self.assertNotIn('yl38_d0', latest.json['reading']['measurements'])
        instant = received.json['received_at']
        history = self.client.get('/api/v1/stations/agrion-demo-001/telemetry', query_string={'from': instant, 'to': instant})
        self.assertEqual(len(history.json['readings']), 1)
        self.assertIsNone(self.client.get('/api/v1/stations/other/telemetry/latest').json['reading'])
        another = create_app({'TESTING': True, 'STATION_DB_PATH': str(Path(self.directory.name) / 'stations.sqlite3'),
                              'STATION_KEYS': {'agrion-demo-001': 'test-secret'}}).test_client()
        self.assertEqual(another.get('/api/v1/stations/agrion-demo-001/telemetry/latest').json['reading']['measurements']['temperature_c'], 26.5)

    def test_rejects_invalid_values_and_query(self):
        for name, value in [('rain_detected', 1), ('humidity_pct', 101), ('temperature_c', '26'), ('vento_estimado_m_s', -1)]:
            body = {'station_id': 'agrion-demo-001', 'measurements': {name: value}}
            self.assertEqual(self.send(body).status_code, 400)
        self.assertEqual(self.client.get('/api/v1/stations/agrion-demo-001/telemetry').status_code, 400)
        self.assertEqual(self.client.get('/api/v1/stations/agrion-demo-001/telemetry', query_string={'from': '2026-01-01T00:00:00Z', 'to': '2026-01-02T00:00:00Z', 'limit': 501}).status_code, 400)


if __name__ == '__main__':
    unittest.main()
