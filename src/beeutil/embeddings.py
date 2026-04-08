"""Scene embeddings: query, compare, and match."""

from __future__ import annotations

import numpy as np
import requests

from ._constants import ODC_API_BASE

TIMEOUT = 10


class EmbeddingsError(Exception):
    """Base exception for embeddings operations."""


class DimensionMismatchError(EmbeddingsError):
    """Vectors have incompatible dimensions."""


def list_embeddings(
    since: int | None = None,
    until: int | None = None,
) -> list[dict]:
    """Query scene embeddings from odc-api."""
    params: dict = {}
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
        raise EmbeddingsError(f'Failed to reach odc-api: {e}') from e

    if resp.status_code != 200:
        raise EmbeddingsError(
            f'odc-api error {resp.status_code}: {resp.text}',
        )

    try:
        items = resp.json()
    except ValueError as e:
        raise EmbeddingsError('Invalid JSON response') from e

    if not isinstance(items, list):
        raise EmbeddingsError(
            f'Expected list, got {type(items).__name__}',
        )

    return items


def fetch_and_match(
    since: int,
    query_embeddings: list[dict],
    default_threshold: float = 0.15,
) -> tuple[list[dict], int]:
    """Fetch new embeddings since a timestamp and return matches.

    since is inclusive — pass last_timestamp_ms + 1 to avoid reprocessing.
    Returns (matches, last_timestamp_ms). Cursor advances even with
    no matches.
    """
    items = list_embeddings(since=since)

    if not items:
        return ([], since)

    last_timestamp_ms = max(item['timestamp_ms'] for item in items)
    all_matches = []

    for item in items:
        matches = find_matches(item, query_embeddings, default_threshold)
        all_matches.extend(matches)

    all_matches.sort(key=lambda m: m['score'], reverse=True)
    return (all_matches, last_timestamp_ms)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Dot product of two vectors. Assumes inputs are L2-normalized."""
    if len(a) != len(b):
        raise DimensionMismatchError(
            f'Vector dimensions do not match: {len(a)} vs {len(b)}',
        )
    return float(np.dot(a, b))


def find_matches(
    embedding_item: dict,
    query_embeddings: list[dict],
    default_threshold: float = 0.15,
) -> list[dict]:
    """Compare a scene embedding against all query embeddings.

    Returns matches above threshold, sorted by score descending.
    """
    embedding_vector = embedding_item['embeddings']
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
                'lat': embedding_item['lat'],
                'lon': embedding_item['lon'],
                'image_name': embedding_item['image_name'],
            })

    matches.sort(key=lambda m: m['score'], reverse=True)
    return matches


def load_query_embeddings(plugin_name: str) -> list[dict]:
    """Load query embeddings from the plugin data store."""
    try:
        resp = requests.get(
            f'{ODC_API_BASE}/plugin/dataStore/{plugin_name}/queryEmbeddings',
            timeout=TIMEOUT,
        )
    except requests.RequestException as e:
        raise EmbeddingsError(f'Failed to reach odc-api: {e}') from e

    if resp.status_code != 200:
        raise EmbeddingsError(
            f'odc-api error {resp.status_code}: {resp.text}',
        )

    try:
        data = resp.json()
    except ValueError as e:
        raise EmbeddingsError('Invalid JSON response') from e

    items = data.get('queryEmbeddings')
    if not isinstance(items, list):
        raise EmbeddingsError('Response missing queryEmbeddings list')

    return items
