import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from app import create_app
from app.services import planning_jobs as jobs


class PlanningJobsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = str(Path(self.temp.name) / 'jobs.sqlite3')
        self.client = create_app({'TESTING': True, 'PLANNING_JOBS_PATH': self.path}).test_client()

    def wait_done(self, job_id):
        for _ in range(200):
            data = jobs.get(self.path, job_id)
            if data['status'] != 'running':
                return data
            time.sleep(.01)
        self.fail('Job did not finish')

    def test_slow_analysis_returns_before_completion_and_other_app_reads_result(self):
        release = threading.Event()
        def slow(context):
            release.wait(5)
            return {'status': 'partial', 'crops': []}
        with patch('app.api.planning.analyze', side_effect=slow), patch('app.api.planning._rate_limit', return_value=True):
            try:
                response = self.client.post('/api/planning/analyze', headers={'Prefer': 'respond-async'},
                    json={'context': {'property': {'id': 'p1'}}, 'inputs': {}})
                self.assertEqual(response.status_code, 202)
                job_id = response.json['job_id']
                other = create_app({'TESTING': True, 'PLANNING_JOBS_PATH': self.path}).test_client()
                status = other.get('/api/planning/jobs/' + job_id)
                self.assertEqual(status.json['status'], 'running')
                self.assertEqual(status.headers['Cache-Control'], 'no-store')
            finally:
                release.set()
            result = self.wait_done(job_id)
            self.assertEqual(result['property_id'], 'p1')
            self.assertEqual(result['result']['status'], 'partial')

    def test_capacity_expiry_and_unknown_id(self):
        now = time.time()
        with jobs.connect(self.path) as db:
            for i in range(jobs.MAX_ACTIVE):
                db.execute('INSERT INTO planning_jobs VALUES (?, ?, ?, ?, NULL)',
                           (str(i), 'p', now, 'running'))
        with self.assertRaises(jobs.CapacityError):
            jobs.submit(self.path, {'property': {'id': 'p'}}, lambda _: {})
        with patch('app.services.planning_jobs.time.time', return_value=now + jobs.JOB_TIMEOUT + 1):
            self.assertEqual(jobs.get(self.path, '0')['status'], 'expired')
        self.assertEqual(self.client.get('/api/planning/jobs/'+'a'*64).status_code, 404)
        self.assertEqual(self.client.get('/api/planning/jobs/invalid').status_code, 404)

    def test_unexpected_exception_is_finite_without_exposing_details(self):
        def fail(_):
            raise RuntimeError('private context')
        job_id = jobs.submit(self.path, {'property': {'id': 'p'}}, fail)
        data = self.wait_done(job_id)
        self.assertEqual(data['status'], 'failed')
        self.assertNotIn('private', str(data))
