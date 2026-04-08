import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from beeutil.embeddings import (
    DimensionMismatchError,
    EmbeddingsError,
    cosine_similarity,
    fetch_and_match,
    find_matches,
    list_embeddings,
    load_query_embeddings,
)

# --- cosine_similarity tests ---


def test_dimension_mismatch():
    with pytest.raises(DimensionMismatchError):
        cosine_similarity([1.0, 0.0, 0.0], [1.0, 0.0])


def test_cosine_similarity_normalized_inputs():
    """Similar normalized embeddings should produce high similarity."""
    # Two similar 8-dim embeddings (e.g., two stop signs from different angles)
    a = [0.41, 0.29, -0.12, 0.55, 0.38, -0.21, 0.33, 0.31]
    b = [0.39, 0.31, -0.10, 0.53, 0.40, -0.19, 0.35, 0.29]
    result = cosine_similarity(a, b)
    assert result > 0.99


def test_cosine_similarity_normalizes_inputs():
    """Non-normalized vectors should still produce correct cosine similarity."""
    # Same direction, different magnitudes — should be 1.0 regardless of scale
    a = [0.3, 0.7, 0.2]
    b = [0.6, 1.4, 0.4]  # 2x of a
    assert cosine_similarity(a, b) == pytest.approx(1.0)

    # Without normalization, dot(a, b) = 0.74 — not a valid cosine similarity.
    # With normalization, result is bounded to [-1, 1]
    c = [0.9, 0.3, 0.5]
    d = [0.1, 0.8, 0.4]
    result = cosine_similarity(c, d)
    assert -1.0 <= result <= 1.0


# --- find_matches tests ---


def _make_embedding_item(
    embedding, ts=1000, lat=37.0, lon=-122.0, filename='test.json',
):
    return {
        'timestamp_ms': ts,
        'image_name': filename,
        'embeddings': embedding,
        'lat': lat,
        'lon': lon,
    }


def test_find_matches_above_threshold():
    item = _make_embedding_item([1.0, 0.0, 0.0])
    qe = [{'label': 'test', 'embedding': [1.0, 0.0, 0.0]}]
    matches = find_matches(item, qe, default_threshold=0.5)
    assert len(matches) == 1
    assert matches[0]['label'] == 'test'
    assert matches[0]['score'] == pytest.approx(1.0)
    assert matches[0]['timestamp_ms'] == 1000
    assert matches[0]['lat'] == 37.0
    assert matches[0]['lon'] == -122.0
    assert matches[0]['image_name'] == 'test.json'


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


def test_find_matches_multiple_matches():
    item = _make_embedding_item([0.8, 0.6, 0.0])
    qe = [
        {'label': 'low', 'embedding': [0.0, 1.0, 0.0], 'threshold': 0.0},
        {'label': 'high', 'embedding': [1.0, 0.0, 0.0], 'threshold': 0.0},
    ]
    matches = find_matches(item, qe, default_threshold=0.0)
    assert len(matches) == 2
    labels = {m['label'] for m in matches}
    assert labels == {'low', 'high'}


def test_find_matches_dimension_mismatch_query_vs_embedding():
    item = _make_embedding_item([1.0, 0.0, 0.0])
    qe = [{'label': 'test', 'embedding': [1.0, 0.0]}]
    with pytest.raises(DimensionMismatchError):
        find_matches(item, qe, default_threshold=0.5)


# --- list_embeddings tests ---


def test_list_embeddings_returns_items():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {
            'image_name': '1000.json', 'timestamp_ms': 1000,
            'lat': 37.0, 'lon': -122.0, 'embeddings': [0.1],
        },
        {
            'image_name': '2000.json', 'timestamp_ms': 2000,
            'lat': 37.1, 'lon': -122.1, 'embeddings': [0.3],
        },
    ]

    with patch('beeutil.embeddings.requests.get', return_value=mock_resp) as mock_get:
        result = list_embeddings(since_ms=500, until_ms=3000)
        assert len(result) == 2
        mock_get.assert_called_once()
        assert mock_get.call_args.kwargs['params'] == {'since': 500, 'until': 3000}


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


# --- fetch_and_match tests ---


def test_fetch_and_match_returns_matches_and_cursor():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {
            'image_name': 'a.json', 'timestamp_ms': 1000,
            'lat': 37.0, 'lon': -122.0,
            'embeddings': [1.0, 0.0, 0.0],
        },
        {
            'image_name': 'b.json', 'timestamp_ms': 2000,
            'lat': 37.1, 'lon': -122.1,
            'embeddings': [0.0, 1.0, 0.0],
        },
    ]
    qe = [{'label': 'target', 'embedding': [1.0, 0.0, 0.0], 'threshold': 0.5}]

    with patch('beeutil.embeddings.requests.get', return_value=mock_resp):
        matches, last_ts = fetch_and_match(0, qe, default_threshold=0.5)
        assert len(matches) == 1
        assert matches[0]['label'] == 'target'
        assert matches[0]['timestamp_ms'] == 1000
        assert last_ts == 2000


def test_fetch_and_match_advances_cursor_even_with_no_matches():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {
            'image_name': 'a.json', 'timestamp_ms': 5000,
            'lat': 37.0, 'lon': -122.0,
            'embeddings': [0.0, 1.0, 0.0],
        },
    ]
    qe = [{'label': 'target', 'embedding': [1.0, 0.0, 0.0], 'threshold': 0.99}]

    with patch('beeutil.embeddings.requests.get', return_value=mock_resp):
        matches, last_ts = fetch_and_match(0, qe, default_threshold=0.5)
        assert matches == []
        assert last_ts == 5000


def test_fetch_and_match_returns_since_when_no_embeddings():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = []

    with patch('beeutil.embeddings.requests.get', return_value=mock_resp):
        matches, last_ts = fetch_and_match(42, [], default_threshold=0.5)
        assert matches == []
        assert last_ts == 42


# --- load_query_embeddings tests ---


def test_load_query_embeddings_returns_items():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        'queryEmbeddings': [{'label': 'stop', 'embedding': [1.0]}],
    }

    with patch('beeutil.embeddings.requests.get', return_value=mock_resp) as mock_get:
        result = load_query_embeddings('my-plugin')
        assert len(result) == 1
        assert result[0]['label'] == 'stop'
        assert 'my-plugin' in mock_get.call_args.args[0]


def test_load_query_embeddings_raises_on_non_200():
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_resp.text = 'not found'

    with (
        patch('beeutil.embeddings.requests.get', return_value=mock_resp),
        pytest.raises(EmbeddingsError, match='404'),
    ):
        load_query_embeddings('my-plugin')


def test_load_query_embeddings_raises_on_missing_key():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {'other': 'data'}

    with (
        patch('beeutil.embeddings.requests.get', return_value=mock_resp),
        pytest.raises(EmbeddingsError, match='queryEmbeddings'),
    ):
        load_query_embeddings('my-plugin')
