"""Recepção e consulta de leituras da mini estação meteorológica."""
import hmac
import json
import math
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify, request

stations_blueprint = Blueprint('stations', __name__)
STATION_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$')
FIELDS = {'rain_detected', 'temperature_c', 'humidity_pct', 'vento_estimado_m_s'}


@contextmanager
def _database():
    path = current_app.config.get('STATION_DB_PATH') or os.environ.get('AGRION_STATION_DB_PATH', '/var/lib/agrion/stations.sqlite3')
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA busy_timeout=10000')
    connection.execute('CREATE TABLE IF NOT EXISTS telemetry (id INTEGER PRIMARY KEY, station_id TEXT NOT NULL, received_at TEXT NOT NULL, rain_detected INTEGER, temperature_c REAL, humidity_pct REAL, vento_estimado_m_s REAL)')
    connection.execute('CREATE INDEX IF NOT EXISTS telemetry_station_time ON telemetry(station_id, received_at DESC, id DESC)')
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def _keys():
    try:
        value = current_app.config.get('STATION_KEYS')
        parsed = value if isinstance(value, dict) else json.loads(os.environ.get('AGRION_STATION_KEYS') or '{}')
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError):
        return {}


def _reading(row):
    return {'station_id': row['station_id'], 'received_at': row['received_at'], 'measurements': {
        'rain_detected': None if row['rain_detected'] is None else bool(row['rain_detected']),
        'temperature_c': row['temperature_c'], 'humidity_pct': row['humidity_pct'],
        'vento_estimado_m_s': row['vento_estimado_m_s']}}


def _date(value):
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError()
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError()
    return parsed.astimezone(timezone.utc).isoformat(timespec='microseconds')


@stations_blueprint.post('/api/v1/stations/telemetry')
def receive_telemetry():
    if request.content_length is not None and request.content_length > 4096:
        return jsonify(error='request_too_large'), 413
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or set(body) != {'station_id', 'measurements'}:
        return jsonify(error='invalid_request'), 400
    station_id, measurements = body['station_id'], body['measurements']
    if not isinstance(station_id, str) or not STATION_ID.fullmatch(station_id) or not isinstance(measurements, dict):
        return jsonify(error='invalid_request'), 400
    key = _keys().get(station_id)
    supplied = request.headers.get('X-Station-Key', '')
    if not isinstance(key, str) or not key or not hmac.compare_digest(key, supplied):
        return jsonify(error='unauthorized'), 401
    values = {name: measurements.get(name) for name in FIELDS}
    if not any(value is not None for value in values.values()):
        return jsonify(error='invalid_measurements'), 400
    if values['rain_detected'] is not None and type(values['rain_detected']) is not bool:
        return jsonify(error='invalid_measurements'), 400
    for name, lower, upper in [('temperature_c', -80, 80), ('humidity_pct', 0, 100), ('vento_estimado_m_s', 0, 100)]:
        value = values[name]
        if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or not lower <= value <= upper):
            return jsonify(error='invalid_measurements'), 400
    received_at = datetime.now(timezone.utc).isoformat(timespec='microseconds')
    try:
        with _database() as db:
            db.execute('INSERT INTO telemetry (station_id, received_at, rain_detected, temperature_c, humidity_pct, vento_estimado_m_s) VALUES (?, ?, ?, ?, ?, ?)',
                       (station_id, received_at, values['rain_detected'], values['temperature_c'], values['humidity_pct'], values['vento_estimado_m_s']))
    except sqlite3.Error:
        current_app.logger.exception('Station telemetry storage failed')
        return jsonify(error='storage_unavailable'), 503
    return jsonify(status='received', station_id=station_id, received_at=received_at), 201


@stations_blueprint.get('/api/v1/stations/<station_id>/telemetry/latest')
def latest_telemetry(station_id):
    if not STATION_ID.fullmatch(station_id):
        return jsonify(error='invalid_station_id'), 400
    try:
        with _database() as db:
            row = db.execute('SELECT * FROM telemetry WHERE station_id=? ORDER BY received_at DESC, id DESC LIMIT 1', (station_id,)).fetchone()
    except sqlite3.Error:
        return jsonify(error='storage_unavailable'), 503
    response = jsonify(station_id=station_id, reading=_reading(row) if row else None)
    response.headers['Cache-Control'] = 'no-store'
    return response


@stations_blueprint.get('/api/v1/stations/<station_id>/telemetry')
def telemetry_history(station_id):
    if not STATION_ID.fullmatch(station_id):
        return jsonify(error='invalid_station_id'), 400
    try:
        start = _date(request.args['from'])
        end = _date(request.args['to'])
        limit = int(request.args.get('limit', '100'))
        if start > end or not 1 <= limit <= 500 or set(request.args) - {'from', 'to', 'limit'}:
            raise ValueError()
    except (KeyError, ValueError, OverflowError):
        return jsonify(error='invalid_query'), 400
    try:
        with _database() as db:
            rows = db.execute('SELECT * FROM telemetry WHERE station_id=? AND received_at>=? AND received_at<=? ORDER BY received_at DESC, id DESC LIMIT ?', (station_id, start, end, limit)).fetchall()
    except sqlite3.Error:
        return jsonify(error='storage_unavailable'), 503
    response = jsonify(station_id=station_id, readings=[_reading(row) for row in rows])
    response.headers['Cache-Control'] = 'no-store'
    return response
