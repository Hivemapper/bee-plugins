"""Recordings: query video files from the device."""

from __future__ import annotations

import logging

import requests

from ._constants import ODC_API_BASE

logger = logging.getLogger(__name__)

TIMEOUT = 10


class RecordingsError(Exception):
    """Error querying recordings."""


def get_videos_by_timerange(start_ms: int, end_ms: int) -> list[str]:
    """Find video files covering a time range.

    Returns file path strings. Returns [] if no videos found.
    """
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

    if not isinstance(data, dict):
        raise RecordingsError(
            f'Expected dict from odc-api, got {type(data).__name__}',
        )

    return data.get('files', [])
