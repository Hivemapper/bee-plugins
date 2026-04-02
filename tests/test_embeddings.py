import sys
import os
import math
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from beeutil.embeddings import (
    cosine_similarity,
    DimensionMismatchError,
    find_matches,
    list_embeddings,
    poll_and_match,
    load_query_embeddings,
    EmbeddingsError,
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
    # Two unit vectors at 45 degrees: cos(45) = sqrt(2)/2 ≈ 0.7071
    a = [math.sqrt(2) / 2, math.sqrt(2) / 2]
    b = [1.0, 0.0]
    assert cosine_similarity(a, b) == pytest.approx(math.sqrt(2) / 2, abs=1e-10)


def test_known_similarity_negative():
    # Two unit vectors at 120 degrees: cos(120) = -0.5
    a = [1.0, 0.0]
    b = [-0.5, math.sqrt(3) / 2]
    assert cosine_similarity(a, b) == pytest.approx(-0.5, abs=1e-10)


def test_realistic_1024d_known_value():
    # Verify against manual dot product computation
    import random
    random.seed(42)
    a = [random.gauss(0, 1) for _ in range(1024)]
    b = [random.gauss(0, 1) for _ in range(1024)]
    # Normalize
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    a = [x / norm_a for x in a]
    b = [x / norm_b for x in b]
    # Compute expected value manually
    expected = sum(x * y for x, y in zip(a, b))
    result = cosine_similarity(a, b)
    assert result == pytest.approx(expected, abs=1e-10)
    assert -1.0 <= result <= 1.0


def test_self_similarity_of_normalized_vector():
    # A normalized vector dotted with itself should be 1.0
    import random
    random.seed(99)
    v = [random.gauss(0, 1) for _ in range(512)]
    norm = math.sqrt(sum(x * x for x in v))
    v = [x / norm for x in v]
    assert cosine_similarity(v, v) == pytest.approx(1.0, abs=1e-10)


def test_dimension_mismatch():
    a = [1.0, 0.0, 0.0]
    b = [1.0, 0.0]
    with pytest.raises(DimensionMismatchError):
        cosine_similarity(a, b)


def test_empty_vectors():
    assert cosine_similarity([], []) == pytest.approx(0.0)


# --- find_matches tests ---

def _make_embedding_item(embedding, ts=1000, lat=37.0, lon=-122.0, filename='test.json'):
    return {
        'timestamp_ms': ts,
        'filename': filename,
        'data': {'embedding': embedding, 'lat': lat, 'lon': lon}
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


def test_find_matches_malformed_item_missing_data():
    item = {'timestamp_ms': 1, 'filename': 'x'}
    qe = [{'label': 'test', 'embedding': [1.0, 0.0, 0.0]}]
    with pytest.raises(KeyError):
        find_matches(item, qe)


def test_find_matches_malformed_item_missing_embedding():
    item = {'timestamp_ms': 1, 'filename': 'x', 'data': {'lat': 0, 'lon': 0}}
    qe = [{'label': 'test', 'embedding': [1.0, 0.0, 0.0]}]
    with pytest.raises(KeyError):
        find_matches(item, qe)


# --- list_embeddings tests ---

def test_list_embeddings_returns_valid_items():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {
            'filename': '1000_37.0_-122.0.json',
            'timestamp_ms': 1000,
            'data': {'lat': 37.0, 'lon': -122.0, 'embedding': [0.1, 0.2]}
        },
        {
            'filename': '2000_37.1_-122.1.json',
            'timestamp_ms': 2000,
            'data': {'lat': 37.1, 'lon': -122.1, 'embedding': [0.3, 0.4]}
        }
    ]

    with patch('beeutil.embeddings.requests.get', return_value=mock_resp) as mock_get:
        result = list_embeddings(since=500, until=3000)
        assert len(result) == 2
        assert result[0]['timestamp_ms'] == 1000
        _, kwargs = mock_get.call_args
        assert kwargs['params'] == {'since': 500, 'until': 3000}
        assert kwargs['timeout'] == 10


def test_list_embeddings_filters_malformed():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {
            'filename': 'good.json',
            'timestamp_ms': 1000,
            'data': {'lat': 37.0, 'lon': -122.0, 'embedding': [0.1]}
        },
        {
            'filename': 'no_embedding.json',
            'timestamp_ms': 2000,
            'data': {'lat': 37.0, 'lon': -122.0}
        },
        {
            'filename': 'no_data.json',
            'timestamp_ms': 3000,
        }
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
        result = list_embeddings()
        assert result == []


def test_list_embeddings_raises_on_non_200():
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = 'error'

    with patch('beeutil.embeddings.requests.get', return_value=mock_resp):
        with pytest.raises(EmbeddingsError):
            list_embeddings()


def test_list_embeddings_raises_on_network_error():
    import requests as req
    with patch('beeutil.embeddings.requests.get', side_effect=req.ConnectionError('refused')):
        with pytest.raises(EmbeddingsError):
            list_embeddings()


def test_list_embeddings_no_params():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = []

    with patch('beeutil.embeddings.requests.get', return_value=mock_resp) as mock_get:
        list_embeddings()
        _, kwargs = mock_get.call_args
        assert kwargs['params'] == {}


def test_list_embeddings_since_only():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = []

    with patch('beeutil.embeddings.requests.get', return_value=mock_resp) as mock_get:
        list_embeddings(since=1000)
        _, kwargs = mock_get.call_args
        assert kwargs['params'] == {'since': 1000}


def test_list_embeddings_until_only():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = []

    with patch('beeutil.embeddings.requests.get', return_value=mock_resp) as mock_get:
        list_embeddings(until=5000)
        _, kwargs = mock_get.call_args
        assert kwargs['params'] == {'until': 5000}


def test_list_embeddings_raises_on_non_list_response():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {'error': 'something went wrong'}

    with patch('beeutil.embeddings.requests.get', return_value=mock_resp):
        with pytest.raises(EmbeddingsError, match='Expected list'):
            list_embeddings()


def test_list_embeddings_raises_on_invalid_json():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.side_effect = ValueError('No JSON')

    with patch('beeutil.embeddings.requests.get', return_value=mock_resp):
        with pytest.raises(EmbeddingsError, match='Invalid JSON'):
            list_embeddings()


def test_list_embeddings_filters_missing_timestamp():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {
            'filename': 'good.json', 'timestamp_ms': 1000,
            'data': {'lat': 37.0, 'lon': -122.0, 'embedding': [0.1]}
        },
        {
            'filename': 'no_ts.json',
            'data': {'lat': 37.0, 'lon': -122.0, 'embedding': [0.1]}
        }
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
            'data': {'lat': 37.0, 'lon': -122.0, 'embedding': [0.1]}
        },
        {
            'filename': 'no_lat.json', 'timestamp_ms': 2000,
            'data': {'embedding': [0.1]}
        }
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
            'data': {'lat': 37.0, 'lon': -122.0, 'embedding': [1.0, 0.0, 0.0]}
        },
        {
            'filename': 'b.json', 'timestamp_ms': 2000,
            'data': {'lat': 37.1, 'lon': -122.1, 'embedding': [0.0, 1.0, 0.0]}
        }
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
            'data': {'lat': 37.0, 'lon': -122.0, 'embedding': [0.0, 1.0, 0.0]}
        }
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


def test_poll_and_match_forwards_since_param():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = []

    with patch('beeutil.embeddings.requests.get', return_value=mock_resp) as mock_get:
        poll_and_match(12345, [])
        _, kwargs = mock_get.call_args
        assert kwargs['params'] == {'since': 12345}


def test_poll_and_match_propagates_error():
    import requests as req
    with patch('beeutil.embeddings.requests.get', side_effect=req.ConnectionError('refused')):
        with pytest.raises(EmbeddingsError):
            poll_and_match(0, [])


# --- load_query_embeddings tests ---

def test_load_query_embeddings_raises_not_available():
    with pytest.raises(EmbeddingsError, match='not yet available'):
        load_query_embeddings('my-plugin')
