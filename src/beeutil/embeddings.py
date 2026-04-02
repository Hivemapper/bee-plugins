"""
Scene embeddings: query, compare, and match.

Two API levels:
  - High-level: poll_and_match() fetches new embeddings and compares
    against query embeddings in one call.
  - Low-level: list_embeddings(), cosine_similarity(), find_matches()
    for custom matching logic.

Usage:
  matches, cursor = beeutil.embeddings.poll_and_match(since, query_embeddings)
  score = beeutil.embeddings.cosine_similarity(vec_a, vec_b)
"""

import logging

import numpy as np
import requests

from ._constants import ODC_API_BASE

logger = logging.getLogger(__name__)

TIMEOUT = 10


class EmbeddingsError(Exception):
    """Base exception for embeddings operations."""
    pass


class DimensionMismatchError(EmbeddingsError):
    """Vectors have incompatible dimensions."""
    pass


def list_embeddings(since: int = None, until: int = None) -> list:
    """Query scene embeddings from odc-api.

    Args:
        since: Unix timestamp in ms (inclusive lower bound)
        until: Unix timestamp in ms (inclusive upper bound)

    Returns:
        List of dicts sorted ascending by timestamp.
        Malformed entries are filtered out with a warning log.
        Returns [] if no embeddings exist.

    Raises:
        EmbeddingsError: If odc-api is unreachable or returns an error
    """
    params = {}
    if since is not None:
        params['since'] = since
    if until is not None:
        params['until'] = until

    try:
        resp = requests.get(
            f'{ODC_API_BASE}/embeddings',
            params=params,
            timeout=TIMEOUT,
        )
    except requests.RequestException as e:
        raise EmbeddingsError(f'Failed to reach odc-api: {e}')

    if resp.status_code != 200:
        raise EmbeddingsError(f'odc-api error {resp.status_code}: {resp.text}')

    try:
        items = resp.json()
    except ValueError:
        raise EmbeddingsError(f'Invalid JSON response from odc-api')

    if not isinstance(items, list):
        raise EmbeddingsError(f'Expected list from odc-api, got {type(items).__name__}')

    valid = []
    for item in items:
        data = item.get('data')
        if not isinstance(data, dict):
            logger.warning('Skipping embedding with missing data: %s', item.get('filename'))
            continue
        if not isinstance(data.get('embedding'), list):
            logger.warning('Skipping embedding with missing/invalid embedding: %s', item.get('filename'))
            continue
        if 'timestamp_ms' not in item or 'filename' not in item:
            logger.warning('Skipping embedding with missing timestamp_ms/filename: %s', item.get('filename'))
            continue
        if 'lat' not in data or 'lon' not in data:
            logger.warning('Skipping embedding with missing lat/lon: %s', item.get('filename'))
            continue
        valid.append(item)

    return valid


def poll_and_match(since: int, query_embeddings: list, default_threshold: float = 0.15) -> tuple:
    """Fetch new embeddings and compare against query embeddings.

    Convenience function that wraps list_embeddings() + find_matches().

    Args:
        since: Unix timestamp in ms (inclusive lower bound). Pass
            last_timestamp_ms + 1 from previous call to avoid reprocessing.
        query_embeddings: List of dicts with 'label', 'embedding',
            and optional 'threshold'
        default_threshold: Fallback threshold if embedding has none

    Returns:
        Tuple of (matches, last_timestamp_ms):
        - matches: list of match dicts sorted by score descending
        - last_timestamp_ms: highest timestamp seen, or input since
          if no new embeddings

    Raises:
        EmbeddingsError: If odc-api is unreachable or returns an error
    """
    items = list_embeddings(since=since)

    if not items:
        return ([], since)

    # odc-api returns results sorted ascending by timestamp (embeddings.ts:125)
    last_timestamp_ms = items[-1]['timestamp_ms']
    all_matches = []

    for item in items:
        matches = find_matches(item, query_embeddings, default_threshold)
        all_matches.extend(matches)

    all_matches.sort(key=lambda m: m['score'], reverse=True)
    return (all_matches, last_timestamp_ms)


def cosine_similarity(a: list, b: list) -> float:
    """Cosine similarity between two L2-normalized vectors.

    Both vectors MUST be unit-length (L2-normalized). This function
    computes the dot product, which equals cosine similarity for
    normalized vectors. Passing non-normalized vectors will produce
    incorrect, unbounded results.

    Args:
        a: list[float] (e.g., 1024-d image embedding)
        b: list[float] (e.g., 1024-d query embedding)

    Returns:
        float: Similarity score (1.0 = identical, 0.0 = orthogonal)

    Raises:
        DimensionMismatchError: If vectors have different lengths
    """
    if len(a) != len(b):
        raise DimensionMismatchError(
            f'Vector dimensions do not match: {len(a)} vs {len(b)}'
        )
    return float(np.dot(a, b))


def find_matches(embedding_item: dict, query_embeddings: list, default_threshold: float = 0.15) -> list:
    """Compare an embedding against all query embeddings.

    Uses per-embedding threshold if present, otherwise default_threshold.

    Args:
        embedding_item: Full embedding dict from list_embeddings().
            Expected shape: {
                'timestamp_ms': int,
                'filename': str,
                'data': {'embedding': list[float], 'lat': float, 'lon': float}
            }
        query_embeddings: List of dicts, each with:
            - 'label' (str, required)
            - 'embedding' (list[float], required)
            - 'threshold' (float, optional)
        default_threshold: Fallback threshold if embedding has none

    Returns:
        List of dicts for matches above threshold, sorted by score descending:
        [{
            label: str,
            score: float,
            margin: float,
            timestamp_ms: int,
            lat: float,
            lon: float,
            filename: str
        }]

        Returns [] if no matches above threshold.
    """
    embedding_vector = embedding_item['data']['embedding']
    matches = []

    for qe in query_embeddings:
        threshold = qe.get('threshold', default_threshold)
        score = cosine_similarity(embedding_vector, qe['embedding'])
        if score >= threshold:
            matches.append({
                'label': qe['label'],
                'score': score,
                'margin': score - threshold,
                'timestamp_ms': embedding_item['timestamp_ms'],
                'lat': embedding_item['data']['lat'],
                'lon': embedding_item['data']['lon'],
                'filename': embedding_item['filename'],
            })

    matches.sort(key=lambda m: m['score'], reverse=True)
    return matches


def load_query_embeddings(plugin_name: str) -> list:
    """Load query embeddings from the backend via odc-api.

    NOTE: Not yet available. Requires CAP-104 (odc-api proxy endpoint).
    For V0, hardcode query embeddings or load from a local file.

    Args:
        plugin_name: Plugin name to fetch query embeddings for

    Returns:
        List of dicts: [{label: str, embedding: list[float], threshold: float|None}]

    Raises:
        EmbeddingsError: If query embeddings cannot be loaded
    """
    raise EmbeddingsError(
        f'load_query_embeddings is not yet available (requires CAP-104). '
        f'For V0, hardcode query embeddings or load from a local file.'
    )
