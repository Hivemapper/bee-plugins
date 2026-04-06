import sys
import os
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from beeutil.recordings import get_videos_by_timerange, RecordingsError


def test_returns_file_paths():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        'files': ['/data/video/1715027100000.mp4', '/data/video/1715027110000.mp4']
    }

    with patch('beeutil.recordings.requests.get', return_value=mock_resp) as mock_get:
        result = get_videos_by_timerange(1715027100000, 1715027130000)
        assert result == ['/data/video/1715027100000.mp4', '/data/video/1715027110000.mp4']
        mock_get.assert_called_once()
        url = mock_get.call_args[0][0]
        assert '/recordings/video/query-by-timestamp-ms/1715027100000/1715027130000' in url


def test_returns_empty_list_when_no_videos():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {'files': []}

    with patch('beeutil.recordings.requests.get', return_value=mock_resp):
        result = get_videos_by_timerange(0, 100)
        assert result == []


def test_raises_on_non_200():
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = 'Internal Server Error'

    with patch('beeutil.recordings.requests.get', return_value=mock_resp):
        with pytest.raises(RecordingsError):
            get_videos_by_timerange(0, 100)


