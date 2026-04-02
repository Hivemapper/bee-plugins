"""
Recordings: query video files from the device.

Shared utility across plugins. Wraps the odc-api recordings endpoint
so plugins can find video clips by time range without knowing endpoint details.

Usage:
  videos = beeutil.recordings.get_videos_by_timerange(start_ms, end_ms)
"""

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

    Video segments are ~10 seconds each (determined by firmware).
    Choose your time range accordingly — e.g., +/- 15 seconds
    around an event timestamp to catch the containing segment.

    Args:
        start_ms: Start timestamp in Unix ms (required)
        end_ms: End timestamp in Unix ms (required)

    Returns:
        List of full file path strings, e.g.:
        ["/data/video/1715027100000.mp4"]

        Returns [] if no videos found for the given range
        (including when /data/video/ does not exist on device).
        Videos may be .mp4 or .h264 format.

    Raises:
        RecordingsError: If odc-api is unreachable or returns an error
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
