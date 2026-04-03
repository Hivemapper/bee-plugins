"""Recordings: query video files from the device."""

import logging

import requests

from ._constants import ODC_API_BASE

logger = logging.getLogger(__name__)

TIMEOUT = 10


class RecordingsError(Exception):
    """Error querying recordings."""
    pass


def get_videos_by_timerange(start_ms: int, end_ms: int) -> list:
    """Find video files covering a time range.

    Args:
        start_ms: Start timestamp in Unix ms
        end_ms: End timestamp in Unix ms

    Returns:
        List of file path strings. Returns [] if no videos found.

    Raises:
        RecordingsError: odc-api unreachable or error response
    """
    url = f'{ODC_API_BASE}/recordings/video/query-by-timestamp-ms/{start_ms}/{end_ms}'
    try:
        resp = requests.get(url, timeout=TIMEOUT)
    except requests.RequestException as e:
        raise RecordingsError(f'Failed to reach odc-api: {e}')

    if resp.status_code != 200:
        raise RecordingsError(f'odc-api error {resp.status_code}: {resp.text}')

    try:
        data = resp.json()
    except ValueError:
        raise RecordingsError('Invalid JSON response from odc-api')

    if not isinstance(data, dict):
        raise RecordingsError(f'Expected dict from odc-api, got {type(data).__name__}')

    return data.get('files', [])
