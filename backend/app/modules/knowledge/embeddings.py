"""Dense embeddings via the Gemini API + sparse BM25 term weights computed in process.

Dense: gemini-embedding-2 (multilingual, Matryoshka; EMBEDDING_DIMENSIONS picks the size).
The model ignores task_type, so the retrieval task is stated with the documented text
prefixes instead. Sparse: BM25 term frequencies over exact word forms (no stemming --
there is no maintained Polish stemmer; inflection and paraphrase are the dense model's
job). Qdrant applies IDF server-side (Modifier.IDF), so no corpus statistics are kept here.
Creating the client does no network I/O, so the API starts fast; tests can swap the embedder.
"""
import hashlib
import logging
import re
import time
from collections import Counter
from typing import Protocol

from google import genai
import httpx
from google.genai import errors, types
from qdrant_client import models

# Gemini batchEmbedContents accepts at most 100 inputs per request.
_BATCH = 100
logger = logging.getLogger(__name__)


class Embedder(Protocol):
    dense_dim: int

    async def embed_passages(self, texts: list[str]) -> tuple[list[list[float] | None], list[models.SparseVector]]: ...

    async def embed_query(self, text: str) -> tuple[list[float] | None, models.SparseVector]: ...

    async def aclose(self) -> None: ...


class Bm25:
    """BM25 document-side term weights; queries weigh each distinct term 1.0.

    score(q, d) = SUM IDF(t) * tf(t, d) * (k + 1) / (tf(t, d) + k * (1 - b + b * |d| / avg_len))
    """

    _NON_WORD = re.compile(r"\W+")

    def __init__(self, k: float = 1.2, b: float = 0.75, avg_len: float = 256.0):
        self.k, self.b, self.avg_len = k, b, avg_len

    @classmethod
    def tokens(cls, text: str) -> list[str]:
        return cls._NON_WORD.sub(" ", text.lower()).split()

    @staticmethod
    def token_id(token: str) -> int:
        # Stable across processes and Python versions (unlike hash()); Qdrant indices are uint32.
        return int.from_bytes(hashlib.blake2b(token.encode(), digest_size=4).digest(), "little")

    @staticmethod
    def _vector(weights: dict[int, float]) -> models.SparseVector:
        return models.SparseVector(indices=list(weights), values=list(weights.values()))

    def passage(self, text: str) -> models.SparseVector:
        tokens = self.tokens(text)
        norm = self.k * (1 - self.b + self.b * len(tokens) / self.avg_len)
        counts: Counter[int] = Counter(self.token_id(t) for t in tokens)
        return self._vector({i: tf * (self.k + 1) / (tf + norm) for i, tf in counts.items()})

    def query(self, text: str) -> models.SparseVector:
        return self._vector({self.token_id(t): 1.0 for t in self.tokens(text)})


class GeminiEmbedder:
    def __init__(self, api_key: str | None, model: str, dimensions: int, timeout_seconds: int = 60):
        self.model = model
        self.dense_dim = dimensions
        self.bm25 = Bm25()
        self._retry_dense_at = 0.0
        self._client = genai.Client(
            api_key=api_key, vertexai=False,
            http_options=types.HttpOptions(
                api_version="v1beta",
                timeout=timeout_seconds * 1000,
                # Ingesting long reports sends many batches; ride out short 429/5xx bursts.
                retry_options=types.HttpRetryOptions(attempts=5, initial_delay=1.0, max_delay=20.0),
            ),
        ) if api_key else None

    async def _dense(self, texts: list[str]) -> list[list[float] | None]:
        if self._client is None or time.monotonic() < self._retry_dense_at:
            return [None] * len(texts)
        out: list[list[float]] = []
        for i in range(0, len(texts), _BATCH):
            # One Content per text: a plain string list would be embedded as a single input.
            try:
                response = await self._client.aio.models.embed_content(
                    model=self.model,
                    contents=[types.Content(parts=[types.Part(text=t)]) for t in texts[i:i + _BATCH]],
                    config=types.EmbedContentConfig(output_dimensionality=self.dense_dim),
                )
            except (errors.APIError, httpx.HTTPError) as exc:
                self._retry_dense_at = time.monotonic() + 60
                logger.warning("Dense embeddings unavailable; using BM25 (%s)", type(exc).__name__)
                return [None] * len(texts)
            out.extend(e.values for e in response.embeddings)
        return out

    async def embed_passages(self, texts: list[str]) -> tuple[list[list[float] | None], list[models.SparseVector]]:
        dense = await self._dense([f"title: none | text: {t}" for t in texts])
        return dense, [self.bm25.passage(t) for t in texts]

    async def embed_query(self, text: str) -> tuple[list[float] | None, models.SparseVector]:
        dense = await self._dense([f"task: search result | query: {text}"])
        return dense[0], self.bm25.query(text)

    async def aclose(self) -> None:
        if self._client:
            await self._client.aio.aclose()
            self._client.close()
