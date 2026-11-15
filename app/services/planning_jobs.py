"""Short HTTP requests around bounded background analyses, shared across workers."""
import json
import logging
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager

logger = logging.getLogger(__name__)
MAX_ACTIVE = 4
JOB_TIMEOUT = 240
RETENTION = 3600
_slots = threading.BoundedSemaphore(MAX_ACTIVE)


class CapacityError(Exception):
    pass


@contextmanager
def connect(path):
    db = sqlite3.connect(path, timeout=5)
    db.row_factory = sqlite3.Row
    try:
        with db:
            db.execute('''CREATE TABLE IF NOT EXISTS planning_jobs
                (id TEXT PRIMARY KEY, property_id TEXT NOT NULL, created REAL NOT NULL,
                 state TEXT NOT NULL, result TEXT)''')
            yield db
    finally:
        db.close()


def expire(db, now):
    db.execute('DELETE FROM planning_jobs WHERE created < ?', (now - RETENTION,))
    db.execute("UPDATE planning_jobs SET state='expired' WHERE state='running' AND created < ?",
               (now - JOB_TIMEOUT,))


def submit(path, context, analyze):
    # Expiry cannot cancel a blocked SDK call; also bound live threads per worker.
    if not _slots.acquire(blocking=False):
        raise CapacityError()
    try:
        return _submit(path, context, analyze)
    except Exception:
        _slots.release()
        raise


def _submit(path, context, analyze):
    job_id = secrets.token_hex(32)
    now = time.time()
    with connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        expire(db, now)
        if db.execute("SELECT count(*) FROM planning_jobs WHERE state='running'").fetchone()[0] >= MAX_ACTIVE:
            raise CapacityError()
        db.execute('INSERT INTO planning_jobs VALUES (?, ?, ?, ?, NULL)',
                   (job_id, context['property']['id'], now, 'running'))

    def run():
        try:
            result = analyze(context)
            state = 'completed'
        except Exception as exc:
            # Never log the property context, model content or credentials.
            logger.error('planning_job_failed job=%s error_type=%s', job_id, type(exc).__name__)
            result, state = None, 'failed'
        try:
            with connect(path) as db:
                expire(db, time.time())
                db.execute("UPDATE planning_jobs SET state=?, result=? WHERE id=? AND state='running'",
                           (state, json.dumps(result, ensure_ascii=False), job_id))
            logger.info('planning_job_finished job=%s state=%s elapsed_seconds=%.1f', job_id, state, time.time()-now)
        except sqlite3.Error:
            logger.error('planning_job_storage_failed job=%s', job_id)

    def guarded_run():
        try:
            run()
        finally:
            _slots.release()

    try:
        threading.Thread(target=guarded_run, name='planning-analysis', daemon=True).start()
    except Exception:
        with connect(path) as db:
            db.execute("UPDATE planning_jobs SET state='failed' WHERE id=?", (job_id,))
        raise
    return job_id


def get(path, job_id):
    with connect(path) as db:
        expire(db, time.time())
        row = db.execute('SELECT * FROM planning_jobs WHERE id=?', (job_id,)).fetchone()
    if row is None:
        return None
    data = {'job_id': row['id'], 'property_id': row['property_id'], 'status': row['state']}
    if row['state'] == 'completed':
        data['result'] = json.loads(row['result'])
    return data
