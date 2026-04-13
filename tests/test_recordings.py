import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from beeutil.recordings import RecordingsError, get_videos_by_timerange


def test_returns_file_paths():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "videos": [
            {"filepath": "/data/video/100.mp4", "timestamp_ms": 100},
            {"filepath": "/data/video/110.mp4", "timestamp_ms": 110},
        ],
    }

    with patch("beeutil.recordings.requests.get", return_value=mock_resp) as mock_get:
        result = get_videos_by_timerange(100, 130)
        assert len(result) == 2
        assert result[0] == {
            "filepath": "/data/video/100.mp4",
            "filename": "100.mp4",
            "timestamp_ms": 100,
        }
        assert result[1] == {
            "filepath": "/data/video/110.mp4",
            "filename": "110.mp4",
            "timestamp_ms": 110,
        }
        url = mock_get.call_args[0][0]
        assert "/recordings/video/query-by-timestamp-ms/100/130" in url


def test_returns_empty_list_when_no_videos():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"videos": []}

    with patch("beeutil.recordings.requests.get", return_value=mock_resp):
        result = get_videos_by_timerange(0, 100)
        assert result == []


def test_raises_on_non_200():
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "Internal Server Error"

    with (
        patch("beeutil.recordings.requests.get", return_value=mock_resp),
        pytest.raises(RecordingsError),
    ):
        get_videos_by_timerange(0, 100)
