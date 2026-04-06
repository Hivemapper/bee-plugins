"""Scene embeddings: query, compare, and match."""

from __future__ import annotations

import logging

import numpy as np
import requests

from ._constants import ODC_API_BASE

logger = logging.getLogger(__name__)

TIMEOUT = 10


class EmbeddingsError(Exception):
    """Base exception for embeddings operations."""


class DimensionMismatchError(EmbeddingsError):
    """Vectors have incompatible dimensions."""


def list_embeddings(
    since: int | None = None,
    until: int | None = None,
) -> list[dict]:
    """Query scene embeddings from odc-api.

    Malformed entries are filtered out. Returns [] if none exist.
    """
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
        raise EmbeddingsError('Invalid JSON response from odc-api') from e

    if not isinstance(items, list):
        raise EmbeddingsError(
            f'Expected list from odc-api, got {type(items).__name__}',
        )

    valid = []
    for item in items:
        data = item.get('data')
        fname = item.get('filename')
        if not isinstance(data, dict):
            logger.warning('Skipping embedding missing data: %s', fname)
            continue
        if not isinstance(data.get('embedding'), list):
            logger.warning('Skipping embedding missing vector: %s', fname)
            continue
        if 'timestamp_ms' not in item or 'filename' not in item:
            logger.warning('Skipping embedding missing fields: %s', fname)
            continue
        if 'lat' not in data or 'lon' not in data:
            logger.warning('Skipping embedding missing lat/lon: %s', fname)
            continue
        valid.append(item)

    return valid


def poll_and_match(
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

    last_timestamp_ms = items[-1]['timestamp_ms']
    all_matches = []

    for item in items:
        matches = find_matches(item, query_embeddings, default_threshold)
        all_matches.extend(matches)

    all_matches.sort(key=lambda m: m['score'], reverse=True)
    return (all_matches, last_timestamp_ms)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Dot product of two L2-normalized vectors."""
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


def load_query_embeddings(plugin_name: str) -> list[dict]:
    """Load query embeddings from the device.

    Blocked on CAP-103 — endpoint TBD.
    """
    raise EmbeddingsError('load_query_embeddings not yet implemented')
