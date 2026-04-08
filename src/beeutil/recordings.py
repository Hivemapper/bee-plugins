"""Recordings: query video files from the device."""

from __future__ import annotations

import requests

from ._constants import ODC_API_BASE

TIMEOUT = 10


class RecordingsError(Exception):
    """Error querying recordings."""


def get_video_paths_by_timerange(start_ms: int, end_ms: int) -> list[str]:
    """Return absolute file paths to videos within a time range."""
    url = (
        f'{ODC_API_BASE}/recordings/video'
        f'/query-by-timestamp-ms/{start_ms}/{end_ms}'
    )
    try:
        resp = requests.get(url, timeout=TIMEOUT)
    except requests.RequestException as e:
        raise RecordingsError(f'Failed to reach odc-api: {e}') from e

    if resp.status_code != 200:
        raise RecordingsError(
            f'odc-api error {resp.status_code}: {resp.text}',
        )

    try:
        data = resp.json()
    except ValueError as e:
        raise RecordingsError('Invalid JSON response from odc-api') from e

    files = data.get('files') if isinstance(data, dict) else None
    if not isinstance(files, list):
        raise RecordingsError('Response missing files list')

    return files
