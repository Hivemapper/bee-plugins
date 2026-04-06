import math
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from beeutil.embeddings import (
    DimensionMismatchError,
    EmbeddingsError,
    cosine_similarity,
    find_matches,
    list_embeddings,
    load_query_embeddings,
    poll_and_match,
)

# --- cosine_similarity tests ---


def test_identical_vectors():
    v = [1.0, 0.0, 0.0]
    assert cosine_similarity(v, v) == pytest.approx(1.0)


def test_orthogonal_vectors():
    a = [1.0, 0.0, 0.0]
    b = [0.0, 1.0, 0.0]
    assert cosine_similarity(a, b) == pytest.approx(0.0)


def test_opposite_vectors():
    a = [1.0, 0.0]
    b = [-1.0, 0.0]
    assert cosine_similarity(a, b) == pytest.approx(-1.0)


def test_known_similarity_value():
    a = [math.sqrt(2) / 2, math.sqrt(2) / 2]
    b = [1.0, 0.0]
    assert cosine_similarity(a, b) == pytest.approx(
        math.sqrt(2) / 2, abs=1e-10,
    )


def test_known_similarity_negative():
    a = [1.0, 0.0]
    b = [-0.5, math.sqrt(3) / 2]
    assert cosine_similarity(a, b) == pytest.approx(-0.5, abs=1e-10)


def test_dimension_mismatch():
    with pytest.raises(DimensionMismatchError):
        cosine_similarity([1.0, 0.0, 0.0], [1.0, 0.0])


def test_empty_vectors():
    assert cosine_similarity([], []) == pytest.approx(0.0)


# --- find_matches tests ---


def _make_embedding_item(
    embedding, ts=1000, lat=37.0, lon=-122.0, filename='test.json',
):
    return {
        'timestamp_ms': ts,
        'filename': filename,
        'data': {'embedding': embedding, 'lat': lat, 'lon': lon},
    }


def test_find_matches_above_threshold():
    item = _make_embedding_item([1.0, 0.0, 0.0])
    qe = [{'label': 'test', 'embedding': [1.0, 0.0, 0.0]}]
    matches = find_matches(item, qe, default_threshold=0.5)
    assert len(matches) == 1
    assert matches[0]['label'] == 'test'
    assert matches[0]['score'] == pytest.approx(1.0)
    assert matches[0]['margin'] == pytest.approx(0.5)
    assert matches[0]['timestamp_ms'] == 1000
    assert matches[0]['lat'] == 37.0
    assert matches[0]['lon'] == -122.0
    assert matches[0]['filename'] == 'test.json'


def test_find_matches_below_threshold():
    item = _make_embedding_item([1.0, 0.0, 0.0])
    qe = [{'label': 'test', 'embedding': [0.0, 1.0, 0.0]}]
    matches = find_matches(item, qe, default_threshold=0.5)
    assert matches == []


def test_find_matches_per_vector_threshold():
    item = _make_embedding_item([1.0, 0.0, 0.0])
    qe = [
        {'label': 'strict', 'embedding': [1.0, 0.0, 0.0], 'threshold': 1.1},
        {'label': 'loose', 'embedding': [1.0, 0.0, 0.0], 'threshold': 0.5},
    ]
    matches = find_matches(item, qe, default_threshold=0.5)
    assert len(matches) == 1
    assert matches[0]['label'] == 'loose'


def test_find_matches_sorted_by_score_descending():
    item = _make_embedding_item([0.8, 0.6, 0.0])
    qe = [
        {'label': 'low', 'embedding': [0.0, 1.0, 0.0], 'threshold': 0.0},
        {'label': 'high', 'embedding': [1.0, 0.0, 0.0], 'threshold': 0.0},
    ]
    matches = find_matches(item, qe, default_threshold=0.0)
    assert len(matches) == 2
    assert matches[0]['label'] == 'high'
    assert matches[1]['label'] == 'low'


def test_find_matches_empty_query_embeddings():
    item = _make_embedding_item([1.0, 0.0, 0.0])
    matches = find_matches(item, [], default_threshold=0.5)
    assert matches == []


def test_find_matches_dimension_mismatch_query_vs_embedding():
    item = _make_embedding_item([1.0, 0.0, 0.0])
    qe = [{'label': 'test', 'embedding': [1.0, 0.0]}]
    with pytest.raises(DimensionMismatchError):
        find_matches(item, qe)


def test_find_matches_mixed_dimension_query_embeddings():
    item = _make_embedding_item([1.0, 0.0, 0.0])
    qe = [
        {'label': 'ok', 'embedding': [1.0, 0.0, 0.0]},
        {'label': 'bad', 'embedding': [1.0, 0.0]},
    ]
    with pytest.raises(DimensionMismatchError):
        find_matches(item, qe)


# --- list_embeddings tests ---


def test_list_embeddings_returns_valid_items():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {
            'filename': '1000.json', 'timestamp_ms': 1000,
            'data': {'lat': 37.0, 'lon': -122.0, 'embedding': [0.1]},
        },
        {
            'filename': '2000.json', 'timestamp_ms': 2000,
            'data': {'lat': 37.1, 'lon': -122.1, 'embedding': [0.3]},
        },
    ]

    with patch('beeutil.embeddings.requests.get', return_value=mock_resp):
        result = list_embeddings(since=500, until=3000)
        assert len(result) == 2
        assert result[0]['timestamp_ms'] == 1000
        assert result[1]['timestamp_ms'] == 2000


def test_list_embeddings_filters_malformed():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {
            'filename': 'good.json', 'timestamp_ms': 1000,
            'data': {'lat': 37.0, 'lon': -122.0, 'embedding': [0.1]},
        },
        {
            'filename': 'no_embedding.json', 'timestamp_ms': 2000,
            'data': {'lat': 37.0, 'lon': -122.0},
        },
        {'filename': 'no_data.json', 'timestamp_ms': 3000},
    ]

    with patch('beeutil.embeddings.requests.get', return_value=mock_resp):
        result = list_embeddings()
        assert len(result) == 1
        assert result[0]['filename'] == 'good.json'


def test_list_embeddings_empty():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = []

    with patch('beeutil.embeddings.requests.get', return_value=mock_resp):
        assert list_embeddings() == []


def test_list_embeddings_raises_on_non_200():
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = 'error'

    with (
        patch('beeutil.embeddings.requests.get', return_value=mock_resp),
        pytest.raises(EmbeddingsError),
    ):
        list_embeddings()


def test_list_embeddings_raises_on_non_list_response():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {'error': 'something went wrong'}

    with (
        patch('beeutil.embeddings.requests.get', return_value=mock_resp),
        pytest.raises(EmbeddingsError, match='Expected list'),
    ):
        list_embeddings()


def test_list_embeddings_raises_on_invalid_json():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.side_effect = ValueError('No JSON')

    with (
        patch('beeutil.embeddings.requests.get', return_value=mock_resp),
        pytest.raises(EmbeddingsError, match='Invalid JSON'),
    ):
        list_embeddings()


def test_list_embeddings_filters_missing_timestamp():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {
            'filename': 'good.json', 'timestamp_ms': 1000,
            'data': {'lat': 37.0, 'lon': -122.0, 'embedding': [0.1]},
        },
        {
            'filename': 'no_ts.json',
            'data': {'lat': 37.0, 'lon': -122.0, 'embedding': [0.1]},
        },
    ]

    with patch('beeutil.embeddings.requests.get', return_value=mock_resp):
        result = list_embeddings()
        assert len(result) == 1
        assert result[0]['filename'] == 'good.json'


def test_list_embeddings_filters_missing_lat_lon():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {
            'filename': 'good.json', 'timestamp_ms': 1000,
            'data': {'lat': 37.0, 'lon': -122.0, 'embedding': [0.1]},
        },
        {
            'filename': 'no_lat.json', 'timestamp_ms': 2000,
            'data': {'embedding': [0.1]},
        },
    ]

    with patch('beeutil.embeddings.requests.get', return_value=mock_resp):
        result = list_embeddings()
        assert len(result) == 1
        assert result[0]['filename'] == 'good.json'


# --- poll_and_match tests ---


def test_poll_and_match_returns_matches_and_cursor():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {
            'filename': 'a.json', 'timestamp_ms': 1000,
            'data': {
                'lat': 37.0, 'lon': -122.0,
                'embedding': [1.0, 0.0, 0.0],
            },
        },
        {
            'filename': 'b.json', 'timestamp_ms': 2000,
            'data': {
                'lat': 37.1, 'lon': -122.1,
                'embedding': [0.0, 1.0, 0.0],
            },
        },
    ]
    qe = [{'label': 'target', 'embedding': [1.0, 0.0, 0.0], 'threshold': 0.5}]

    with patch('beeutil.embeddings.requests.get', return_value=mock_resp):
        matches, last_ts = poll_and_match(0, qe)
        assert len(matches) == 1
        assert matches[0]['label'] == 'target'
        assert matches[0]['timestamp_ms'] == 1000
        assert last_ts == 2000


def test_poll_and_match_advances_cursor_even_with_no_matches():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {
            'filename': 'a.json', 'timestamp_ms': 5000,
            'data': {
                'lat': 37.0, 'lon': -122.0,
                'embedding': [0.0, 1.0, 0.0],
            },
        },
    ]
    qe = [{'label': 'target', 'embedding': [1.0, 0.0, 0.0], 'threshold': 0.99}]

    with patch('beeutil.embeddings.requests.get', return_value=mock_resp):
        matches, last_ts = poll_and_match(0, qe)
        assert matches == []
        assert last_ts == 5000


def test_poll_and_match_returns_since_when_no_embeddings():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = []

    with patch('beeutil.embeddings.requests.get', return_value=mock_resp):
        matches, last_ts = poll_and_match(42, [])
        assert matches == []
        assert last_ts == 42


# --- load_query_embeddings tests ---


def test_load_query_embeddings_raises_not_implemented():
    with pytest.raises(EmbeddingsError, match='not yet implemented'):
        load_query_embeddings('my-plugin')
