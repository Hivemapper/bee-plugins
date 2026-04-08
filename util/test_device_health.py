#!/usr/bin/env python3
import sys
import os
import json
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import beeutil.device_health as device_health


def _mock_response(json_data, status_code=200):
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_data
    return mock


class TestCheckClockSync:
    @patch('beeutil.device_health.requests.get')
    def test_synced_clock(self, mock_get):
        mock_get.return_value = _mock_response({
            'syncd': {
                'system_time': '2026-03-23 16:30:00.000000000',
                'utc_time': '2026-03-23 16:30:05.000000000',
                'uptime_ms': 100000,
            },
            'request_uptime_ms': 100100,
        })

        result = device_health.check_clock_sync()
        assert result['synced'] is True
        assert result['drift_secs'] == 5.0
        assert result['error'] is None

    @patch('beeutil.device_health.requests.get')
    def test_drifted_clock_cap96(self, mock_get):
        """Reproduce CAP-96: system clock ~14 months behind GNSS time."""
        mock_get.return_value = _mock_response({
            'syncd': {
                'system_time': '2025-01-13 19:55:00.000000000',
                'utc_time': '2026-03-23 16:30:00.000000000',
                'uptime_ms': 100000,
            },
            'request_uptime_ms': 100100,
        })

        result = device_health.check_clock_sync()
        assert result['synced'] is False
        assert result['drift_secs'] > 60
        assert result['system_time'] == '2025-01-13 19:55:00.000000000'
        assert result['gnss_time'] == '2026-03-23 16:30:00.000000000'
        assert result['error'] is None

    @patch('beeutil.device_health.requests.get')
    def test_api_unreachable(self, mock_get):
        import requests as req
        mock_get.side_effect = req.ConnectionError('Connection refused')

        result = device_health.check_clock_sync()
        assert result['synced'] is False
        assert result['error'] is not None


class TestCheckGpsLock:
    @patch('beeutil.device_health.requests.get')
    def test_gps_locked(self, mock_get):
        def side_effect(url, **kwargs):
            if '/info' in url:
                return _mock_response({'hasGnssLock': True, 'internetIsHealthy': True})
            if '/latestValid' in url:
                return _mock_response({
                    'fix': '3D',
                    'gnss_fix_ok': 1,
                    'satellites_used': 12,
                })
            return _mock_response({}, 404)

        mock_get.side_effect = side_effect

        result = device_health.check_gps_lock()
        assert result['locked'] is True
        assert result['fix'] == '3D'
        assert result['gnss_fix_ok'] == 1
        assert result['satellites_used'] == 12

    @patch('beeutil.device_health.requests.get')
    def test_gps_unlocked_despite_valid_fix(self, mock_get):
        """CAP-96 scenario: GNSS has valid fix but odc-api reports not locked."""
        def side_effect(url, **kwargs):
            if '/info' in url:
                return _mock_response({'hasGnssLock': False})
            if '/latestValid' in url:
                return _mock_response({
                    'fix': '3D',
                    'gnss_fix_ok': 1,
                    'satellites_used': 10,
                })
            return _mock_response({}, 404)

        mock_get.side_effect = side_effect

        result = device_health.check_gps_lock()
        assert result['locked'] is False
        assert result['gnss_fix_ok'] == 1


class TestCheckSession:
    @patch('beeutil.device_health.requests.get')
    def test_session_ready(self, mock_get):
        def side_effect(url, **kwargs):
            if '/ping' in url:
                return _mock_response({
                    'sessionId': 'abc-123',
                    'lockTime': 15.2,
                })
            if '/cameraReady' in url:
                return _mock_response({'isReady': True})
            return _mock_response({}, 404)

        mock_get.side_effect = side_effect

        result = device_health.check_session()
        assert result['session_id'] == 'abc-123'
        assert result['camera_ready'] is True
        assert result['lock_time'] == 15.2

    @patch('beeutil.device_health.requests.get')
    def test_camera_not_ready(self, mock_get):
        def side_effect(url, **kwargs):
            if '/ping' in url:
                return _mock_response({'sessionId': None, 'lockTime': 0})
            if '/cameraReady' in url:
                return _mock_response({'isReady': False})
            return _mock_response({}, 404)

        mock_get.side_effect = side_effect

        result = device_health.check_session()
        assert result['camera_ready'] is False


class TestCheck:
    @patch('beeutil.device_health.requests.get')
    def test_healthy_device(self, mock_get):
        def side_effect(url, **kwargs):
            if '/time/latest' in url:
                return _mock_response({
                    'syncd': {
                        'system_time': '2026-03-23 16:30:00.000',
                        'utc_time': '2026-03-23 16:30:02.000',
                        'uptime_ms': 100000,
                    },
                    'request_uptime_ms': 100100,
                })
            if '/info' in url:
                return _mock_response({
                    'hasGnssLock': True,
                    'internetIsHealthy': True,
                })
            if '/latestValid' in url:
                return _mock_response({
                    'fix': '3D', 'gnss_fix_ok': 1, 'satellites_used': 12,
                })
            if '/ping' in url:
                return _mock_response({
                    'sessionId': 'sess-1', 'lockTime': 10,
                })
            if '/cameraReady' in url:
                return _mock_response({'isReady': True})
            if '/unprocessed' in url:
                return _mock_response({'count': 5, 'frames': 50})
            return _mock_response({}, 404)

        mock_get.side_effect = side_effect

        result = device_health.check()
        assert result['healthy'] is True
        assert len(result['warnings']) == 0

    @patch('beeutil.device_health.requests.get')
    def test_cap96_failure_cascade(self, mock_get):
        """Full CAP-96 scenario: clock drift -> GPS not locked -> warnings."""
        def side_effect(url, **kwargs):
            if '/time/latest' in url:
                return _mock_response({
                    'syncd': {
                        'system_time': '2025-01-13 19:55:00.000',
                        'utc_time': '2026-03-23 16:30:00.000',
                        'uptime_ms': 100000,
                    },
                    'request_uptime_ms': 100100,
                })
            if '/info' in url:
                return _mock_response({
                    'hasGnssLock': False,
                    'internetIsHealthy': False,
                })
            if '/latestValid' in url:
                return _mock_response({
                    'fix': '3D', 'gnss_fix_ok': 1, 'satellites_used': 10,
                })
            if '/ping' in url:
                return _mock_response({
                    'sessionId': None, 'lockTime': 0,
                })
            if '/cameraReady' in url:
                return _mock_response({'isReady': False})
            if '/unprocessed' in url:
                return _mock_response({'count': 0, 'frames': 0})
            return _mock_response({}, 404)

        mock_get.side_effect = side_effect

        result = device_health.check()
        assert result['healthy'] is False
        assert len(result['warnings']) >= 3

        warning_text = ' '.join(result['warnings'])
        assert 'clock' in warning_text.lower() or 'drift' in warning_text.lower()
        assert 'GPS is not locked' in warning_text
        assert 'internet' in warning_text.lower() or 'connectivity' in warning_text.lower()

    @patch('beeutil.device_health.requests.get')
    def test_all_endpoints_down(self, mock_get):
        """Device unreachable — should not crash, should report errors."""
        import requests as req
        mock_get.side_effect = req.ConnectionError('Connection refused')

        result = device_health.check()
        assert result['healthy'] is False
        assert len(result['warnings']) > 0


try:
    from util.state_dump import _analyze_log_file, _analyze_clock_sync
    _has_state_dump = True
except ImportError:
    _has_state_dump = False


@pytest.mark.skipif(not _has_state_dump, reason='paramiko not installed')
class TestLogAnalysis:
    def test_analyze_log_patterns(self, tmp_path):

        log = tmp_path / 'odc-api.log'
        log.write_text(
            'INFO: Starting up\n'
            'WARN: GPS is not locked, skipping cleanup\n'
            'WARN: GPS is not locked, skipping cleanup\n'
            'INFO: Waiting for session to be ready\n'
            'INFO: Nothing to pack, waiting for finished FrameKMs...\n'
            'ERROR: redis: dial tcp: lookup localhost: i/o timeout\n'
            'INFO: normal operation\n'
        )

        findings = _analyze_log_file(str(log))
        patterns_found = {f['pattern'] for f in findings}

        assert 'gps_not_locked' in patterns_found
        assert 'session_not_ready' in patterns_found
        assert 'nothing_to_pack' in patterns_found
        assert 'redis_timeout' in patterns_found

        gps_finding = next(f for f in findings if f['pattern'] == 'gps_not_locked')
        assert gps_finding['count'] == 2
        assert gps_finding['severity'] == 'high'

    def test_clean_log(self, tmp_path):
        pass  # imported at module level

        log = tmp_path / 'clean.log'
        log.write_text('INFO: All systems nominal\nINFO: Processing complete\n')

        findings = _analyze_log_file(str(log))
        assert len(findings) == 0


@pytest.mark.skipif(not _has_state_dump, reason='paramiko not installed')
class TestClockSyncAnalysis:
    def test_analyze_drifted_clock(self):
        pass  # imported at module level

        api_results = {
            '/api/1/time/latest': {
                'syncd': {
                    'system_time': '2025-01-13 19:55:00.000',
                    'utc_time': '2026-03-23 16:30:00.000',
                },
            },
            '/api/1/info': {
                'hasGnssLock': False,
                'internetIsHealthy': False,
            },
            '/api/1/gnssConcise/latestValid': {
                'fix': '3D',
                'gnss_fix_ok': 1,
                'satellites_used': 10,
            },
        }

        diag = _analyze_clock_sync(api_results)
        assert diag['clock_synced'] is False
        assert diag['drift_secs'] > 0
        assert diag['gps_locked'] is False
        assert len(diag['warnings']) >= 2  # clock drift + GPS not locked

    def test_analyze_healthy_device(self):
        pass  # imported at module level

        api_results = {
            '/api/1/time/latest': {
                'syncd': {
                    'system_time': '2026-03-23 16:30:00.000',
                    'utc_time': '2026-03-23 16:30:03.000',
                },
            },
            '/api/1/info': {
                'hasGnssLock': True,
                'internetIsHealthy': True,
            },
        }

        diag = _analyze_clock_sync(api_results)
        assert diag['clock_synced'] is True
        assert len(diag['warnings']) == 0
