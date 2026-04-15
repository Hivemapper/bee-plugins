"""Scene embeddings: query, compare, and match."""

from __future__ import annotations

from typing import TypedDict

import numpy as np
import requests

from ._constants import ODC_API_BASE


class QueryEmbedding(TypedDict):
    label: str
    embedding: list[float]
    threshold: float


class FrameEmbedding(TypedDict):
    embeddings: list[float]
    timestamp_ms: int
    lat: float
    lon: float
    image_name: str


class Match(TypedDict):
    label: str
    score: float
    timestamp_ms: int
    lat: float
    lon: float
    image_name: str


TIMEOUT = 10


class EmbeddingsError(Exception):
    """Base exception for embeddings operations."""


class DimensionMismatchError(EmbeddingsError):
    """Vectors have incompatible dimensions."""


def list_embeddings(
    since_ms: int | None = None,
    until_ms: int | None = None,
) -> list[FrameEmbedding]:
    """Query scene embeddings from odc-api."""
    try:
        resp = requests.get(
            f"{ODC_API_BASE}/embeddings",
            params={"since": since_ms, "until": until_ms},
            timeout=TIMEOUT,
        )
    except requests.RequestException as e:
        raise EmbeddingsError(f"Failed to reach odc-api: {e}") from e

    if resp.status_code != 200:
        raise EmbeddingsError(
            f"odc-api error {resp.status_code}: {resp.text}",
        )

    try:
        items = resp.json()
    except ValueError as e:
        raise EmbeddingsError("Invalid JSON response") from e

    if not isinstance(items, list):
        raise EmbeddingsError(
            f"Expected list, got {type(items).__name__}",
        )

    return items


def load_query_embeddings(plugin_name: str) -> list[QueryEmbedding]:
    """Load query embeddings from the plugin data store."""
    try:
        resp = requests.get(
            f"{ODC_API_BASE}/plugin/dataStore/{plugin_name}/queryEmbeddings",
            timeout=TIMEOUT,
        )
    except requests.RequestException as e:
        raise EmbeddingsError(f"Failed to reach odc-api: {e}") from e

    if resp.status_code != 200:
        raise EmbeddingsError(
            f"odc-api error {resp.status_code}: {resp.text}",
        )

    try:
        data = resp.json()
    except ValueError as e:
        raise EmbeddingsError("Invalid JSON response") from e

    items = data.get("queryEmbeddings")
    if not isinstance(items, list):
        raise EmbeddingsError("Response missing queryEmbeddings list")

    return items


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors. Normalizes inputs internally."""
    if len(a) != len(b):
        raise DimensionMismatchError(
            f"Vector dimensions do not match: {len(a)} vs {len(b)}",
        )
    a_arr, b_arr = np.array(a), np.array(b)
    return float(np.dot(a_arr, b_arr) / (np.linalg.norm(a_arr) * np.linalg.norm(b_arr)))


def find_matches(
    frame_embedding: FrameEmbedding,
    query_embeddings: list[QueryEmbedding],
    default_threshold: float,
) -> list[Match]:
    """Compare a scene embedding against all query embeddings.

    Returns matches above threshold.
    """
    embedding_vector = frame_embedding["embeddings"]
    matches: list[Match] = []

    for qe in query_embeddings:
        threshold = qe.get("threshold", default_threshold)
        score = cosine_similarity(embedding_vector, qe["embedding"])
        if score >= threshold:
            matches.append(
                Match(
                    label=qe["label"],
                    score=score,
                    timestamp_ms=frame_embedding["timestamp_ms"],
                    lat=frame_embedding["lat"],
                    lon=frame_embedding["lon"],
                    image_name=frame_embedding["image_name"],
                )
            )

    return matches


def fetch_and_match(
    since_ms: int,
    query_embeddings: list[QueryEmbedding],
    default_threshold: float,
) -> tuple[list[Match], int]:
    """Fetch new embeddings and return matches with cursor.

    Args:
        since_ms: Inclusive lower bound (Unix ms). Pass cursor + 1 to skip reprocessed.
        query_embeddings: Vectors to match against.
        default_threshold: Minimum cosine similarity for a match.

    Returns:
        (matches, last_timestamp_ms) — cursor advances even with no matches.
    """
    frames = list_embeddings(since_ms=since_ms)

    if not frames:
        return ([], since_ms)

    last_timestamp_ms = since_ms
    all_matches: list[Match] = []

    for frame in frames:
        last_timestamp_ms = max(last_timestamp_ms, frame["timestamp_ms"])
        matches = find_matches(frame, query_embeddings, default_threshold)
        all_matches.extend(matches)

    return (all_matches, last_timestamp_ms)
