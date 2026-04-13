"""Recordings: query video files from the device."""

from __future__ import annotations

import requests
from typing_extensions import TypedDict

from ._constants import ODC_API_BASE


class VideoFile(TypedDict):
    filepath: str
    filename: str
    timestamp_ms: int


TIMEOUT = 10


class RecordingsError(Exception):
    """Error querying recordings."""


def get_videos_by_timerange(start_ms: int, end_ms: int) -> list[VideoFile]:
    """Return video files within a time range."""
    url = f"{ODC_API_BASE}/recordings/video/query-by-timestamp-ms/{start_ms}/{end_ms}"
    try:
        resp = requests.get(url, timeout=TIMEOUT)
    except requests.RequestException as e:
        raise RecordingsError(f"Failed to reach odc-api: {e}") from e

    if resp.status_code != 200:
        raise RecordingsError(
            f"odc-api error {resp.status_code}: {resp.text}",
        )

    try:
        data = resp.json()
    except ValueError as e:
        raise RecordingsError("Invalid JSON response from odc-api") from e

    videos = data.get("videos") if isinstance(data, dict) else None
    if not isinstance(videos, list):
        raise RecordingsError("Response missing videos list")

    return [
        {
            "filepath": item["filepath"],
            "filename": item["filepath"].rsplit("/", 1)[-1],
            "timestamp_ms": item["timestamp_ms"],
        }
        for item in videos
    ]
