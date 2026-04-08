"""
Device health monitoring for Bee plugins.

Provides functions to check GPS lock, clock synchronization, session
readiness, and overall device health. Designed to detect the failure
cascade identified in CAP-96: clock drift -> GPS unlock -> session
not ready -> no FrameKMs -> no AI events uploaded.

Usage:
    import beeutil

    health = beeutil.device_health.check()
    if not health['healthy']:
        for w in health['warnings']:
            print(f'WARNING: {w}')
"""

import logging
import time

import requests

ODC_API_BASE = 'http://127.0.0.1:5000/api/1'
REQUEST_TIMEOUT = 5

# Maximum acceptable drift (seconds) between system clock and GNSS time
MAX_CLOCK_DRIFT_SECS = 60

logger = logging.getLogger(__name__)


def _get(endpoint):
    """GET an odc-api endpoint, return parsed JSON or None on failure."""
    url = f'{ODC_API_BASE}{endpoint}'
    try:
        res = requests.get(url, timeout=REQUEST_TIMEOUT)
        if res.status_code == 200:
            return res.json()
    except requests.RequestException as e:
        logger.debug(f'device_health: {endpoint} failed: {e}')
    return None


def get_device_info():
    """Query /api/1/info for device status including GNSS lock and internet."""
    return _get('/info')


def get_time_sync():
    """Query /api/1/time/latest for system vs GNSS time comparison.

    Returns dict with keys:
        syncd.system_time  - device system clock timestamp
        syncd.utc_time     - GNSS UTC timestamp
        syncd.uptime_ms    - uptime when GNSS sample was taken
        request_uptime_ms  - uptime at request time
    """
    return _get('/time/latest')


def get_gps_sample():
    """Query /api/1/gps/sample for the latest GPS fix details."""
    return _get('/gps/sample')


def get_gnss_latest():
    """Query /api/1/gnssConcise/latestValid for latest valid GNSS record."""
    return _get('/gnssConcise/latestValid')


def get_ping():
    """Query /api/1/ping for session and lock time info."""
    return _get('/ping')


def get_framekm_status():
    """Query /api/1/framekm/unprocessed for pending FrameKM count."""
    return _get('/framekm/unprocessed')


def get_camera_ready():
    """Query /api/1/recordings/cameraReady for camera/inference readiness."""
    return _get('/recordings/cameraReady')


def check_clock_sync():
    """Compare system time to GNSS time and detect dangerous drift.

    Returns:
        dict with keys:
            synced (bool): True if clock drift is within MAX_CLOCK_DRIFT_SECS
            drift_secs (float|None): Estimated drift in seconds, or None if unavailable
            system_time (str|None): System time string from device
            gnss_time (str|None): GNSS UTC time string from device
            error (str|None): Error message if check could not be performed
    """
    result = {
        'synced': False,
        'drift_secs': None,
        'system_time': None,
        'gnss_time': None,
        'error': None,
    }

    data = get_time_sync()
    if data is None:
        result['error'] = 'Could not reach /api/1/time/latest'
        return result

    syncd = data.get('syncd')
    if not syncd:
        result['error'] = 'No syncd data in time response'
        return result

    result['system_time'] = syncd.get('system_time')
    result['gnss_time'] = syncd.get('utc_time')

    # Estimate drift using uptime difference: the GNSS sample was taken at
    # syncd.uptime_ms, and the API request was served at request_uptime_ms.
    # The gap tells us how stale the GNSS reading is but not the drift itself.
    # For drift, compare the two wall-clock timestamps.
    sys_time_str = syncd.get('system_time', '')
    utc_time_str = syncd.get('utc_time', '')

    if not sys_time_str or not utc_time_str:
        result['error'] = 'Missing time fields in syncd response'
        return result

    try:
        # Timestamps are like "2025-01-13 19:55:00.123456789"
        # Parse to seconds precision (enough for drift detection)
        from datetime import datetime
        fmt = '%Y-%m-%d %H:%M:%S'
        sys_dt = datetime.strptime(sys_time_str[:19], fmt)
        utc_dt = datetime.strptime(utc_time_str[:19], fmt)
        drift = abs((sys_dt - utc_dt).total_seconds())
        result['drift_secs'] = drift
        result['synced'] = drift <= MAX_CLOCK_DRIFT_SECS
    except (ValueError, TypeError) as e:
        result['error'] = f'Failed to parse time: {e}'

    return result


def check_gps_lock():
    """Check whether the device has a GNSS lock.

    Returns:
        dict with keys:
            locked (bool): True if GPS is locked
            fix (str|None): Fix type (e.g. '3D', '2D', 'No fix')
            gnss_fix_ok (int|None): 1 if fix is valid
            satellites_used (int|None): Number of satellites in fix
            error (str|None): Error message if check failed
    """
    result = {
        'locked': False,
        'fix': None,
        'gnss_fix_ok': None,
        'satellites_used': None,
        'error': None,
    }

    # Primary check: /api/1/info has hasGnssLock
    info = get_device_info()
    if info is not None:
        result['locked'] = bool(info.get('hasGnssLock', False))

    # Supplementary: get detailed GNSS data
    gnss = get_gnss_latest()
    if gnss is not None:
        result['fix'] = gnss.get('fix')
        result['gnss_fix_ok'] = gnss.get('gnss_fix_ok')
        result['satellites_used'] = gnss.get('satellites_used')
    elif info is None:
        result['error'] = 'Could not reach GPS endpoints'

    return result


def check_session():
    """Check session and camera readiness.

    Returns:
        dict with keys:
            session_id (str|None): Current session ID
            camera_ready (bool): Whether inference pipeline is ready
            lock_time (float|None): Time-to-first-fix in seconds
            error (str|None): Error message if check failed
    """
    result = {
        'session_id': None,
        'camera_ready': False,
        'lock_time': None,
        'error': None,
    }

    ping = get_ping()
    if ping is not None:
        result['session_id'] = ping.get('sessionId')
        result['lock_time'] = ping.get('lockTime')

    cam = get_camera_ready()
    if cam is not None:
        result['camera_ready'] = bool(cam.get('isReady', False))
    elif ping is None:
        result['error'] = 'Could not reach session/camera endpoints'

    return result


def check():
    """Run a comprehensive device health check.

    Detects the CAP-96 failure cascade:
        1. Clock not synced to GNSS time
        2. GPS not locked (despite valid GNSS fix)
        3. Session not ready
        4. No internet connectivity

    Returns:
        dict with keys:
            healthy (bool): True if no warnings
            warnings (list[str]): Human-readable warning messages
            clock (dict): Output of check_clock_sync()
            gps (dict): Output of check_gps_lock()
            session (dict): Output of check_session()
            internet (bool|None): Whether internet is healthy
            framekm (dict|None): Unprocessed FrameKM status
    """
    warnings = []

    clock = check_clock_sync()
    gps = check_gps_lock()
    session = check_session()

    info = get_device_info()
    internet = info.get('internetIsHealthy') if info else None

    framekm = get_framekm_status()

    # Analyze for CAP-96 pattern
    if clock.get('error'):
        warnings.append(f'Clock sync check failed: {clock["error"]}')
    elif not clock['synced']:
        drift = clock.get('drift_secs')
        warnings.append(
            f'System clock not synced to GNSS time (drift: {drift:.0f}s). '
            f'System: {clock["system_time"]}, GNSS: {clock["gnss_time"]}'
        )

    if gps.get('error'):
        warnings.append(f'GPS check failed: {gps["error"]}')
    elif not gps['locked']:
        detail = ''
        if gps.get('gnss_fix_ok') == 1:
            detail = (
                ' GNSS module reports valid fix '
                f'(fix={gps["fix"]}, gnss_fix_ok=1) but odc-api does not '
                'consider GPS locked -- likely due to clock drift (CAP-96)'
            )
        warnings.append(f'GPS is not locked.{detail}')

    if session.get('error'):
        warnings.append(f'Session check failed: {session["error"]}')
    elif not session['camera_ready']:
        warnings.append('Camera/inference pipeline is not ready')

    if internet is False:
        warnings.append('No internet connectivity (uploads will fail)')

    if framekm is not None and framekm.get('count', 0) == 0 and framekm.get('frames', 0) == 0:
        if gps['locked'] and session['camera_ready']:
            warnings.append(
                'No FrameKMs pending despite GPS lock and camera ready -- '
                'session may not be generating data'
            )

    return {
        'healthy': len(warnings) == 0,
        'warnings': warnings,
        'clock': clock,
        'gps': gps,
        'session': session,
        'internet': internet,
        'framekm': framekm,
    }
