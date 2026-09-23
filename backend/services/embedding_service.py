from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Any

from huggingface_hub import InferenceClient

from backend.core.config import settings


client = InferenceClient(model=settings.HF_MODEL, token=settings.HF_TOKEN, timeout=1.5)
_executor = ThreadPoolExecutor(max_workers=2)


def get_embedding(text: str) -> list[float]:
    if not text or not text.strip():
        raise ValueError("Embedding input is empty.")
    response = client.feature_extraction(text=text, model=settings.HF_MODEL)
    if isinstance(response, list):
        flat = response
        if len(flat) > 0 and isinstance(flat[0], list):
            flat = [item for sub in flat for item in sub]
        return [float(v) for v in flat]
    if isinstance(response, dict):
        values = response.get("embedding") or response.get("data") or response.get("vector")
        if values is not None:
            return [float(v) for v in values]
        raise ValueError(f"Unsupported embedding response shape: {response}")
    raise ValueError(f"Unsupported embedding response type: {type(response)}")


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    if len(vec_a) != len(vec_b):
        raise ValueError("Embedding dimensions do not match.")
    if not vec_a:
        raise ValueError("Empty embedding vector.")
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0 or norm_b == 0:
        raise ValueError("Embedding vector has zero norm.")
    return dot / (norm_a * norm_b)


def calculate_similarity(text_a: str, text_b: str) -> float:
    vec_a = _executor.submit(get_embedding, text_a).result(timeout=1.5)
    vec_b = _executor.submit(get_embedding, text_b).result(timeout=1.5)
    return max(0.0, min(1.0, (_cosine_similarity(vec_a, vec_b) + 1.0) / 2.0))
