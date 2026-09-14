"""
Shared embedding + reranking stack for the RAG pipeline.

- Embeddings: sentence-transformers (default BAAI/bge-small-en-v1.5, 384-dim),
  with the bge query instruction prefix for asymmetric retrieval.
- Reranking: a cross-encoder (default cross-encoder/ms-marco-MiniLM-L-6-v2)
  rescores the candidate pool; final relevance scores are sigmoid(logit) on a
  clean 0-1 scale, which the RELEVANCE_CUTOFF gate operates on.

Models are loaded lazily once per process and cached; all failures fall back
to Chroma's DefaultEmbeddingFunction so retrieval never hard-crashes.
"""
import logging
import math
import os
import threading
from typing import List, Optional

# transformers must never touch its TF backend in this environment
# (Keras 3 breaks the import); forces the PyTorch path.
os.environ.setdefault("USE_TF", "0")

from app.config import settings

logger = logging.getLogger("lenny_growth.rag.embeddings")

BGE_QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "

_embedding_model = None
_embedding_model_name: Optional[str] = None
_reranker = None
_reranker_model_name: Optional[str] = None
_lock = threading.Lock()


def get_embedding_model():
    """Lazy singleton for the sentence-transformers embedding model."""
    global _embedding_model, _embedding_model_name
    name = settings.EMBEDDING_MODEL
    if _embedding_model is None or _embedding_model_name != name:
        with _lock:
            if _embedding_model is None or _embedding_model_name != name:
                from sentence_transformers import SentenceTransformer
                logger.info(f"Loading embedding model: {name}")
                _embedding_model = SentenceTransformer(name)
                _embedding_model_name = name
    return _embedding_model


def get_reranker():
    """Lazy singleton for the cross-encoder reranker."""
    global _reranker, _reranker_model_name
    name = settings.RERANKER_MODEL
    if _reranker is None or _reranker_model_name != name:
        with _lock:
            if _reranker is None or _reranker_model_name != name:
                from sentence_transformers import CrossEncoder
                logger.info(f"Loading reranker model: {name}")
                _reranker = CrossEncoder(name)
                _reranker_model_name = name
    return _reranker


def embed_texts(texts: List[str], is_query: bool = False) -> List[List[float]]:
    """Embed texts with the configured model, L2-normalized for cosine distance."""
    if not texts:
        return []
    model = get_embedding_model()
    inputs = list(texts)
    if is_query and settings.EMBED_QUERY_INSTRUCTION and settings.EMBEDDING_MODEL.lower().startswith("baai/bge"):
        inputs = [BGE_QUERY_INSTRUCTION + t for t in inputs]
    vectors = model.encode(inputs, normalize_embeddings=True, show_progress_bar=False)
    return [v.tolist() for v in vectors]


def rerank_pairs(query: str, excerpts: List[str]) -> List[float]:
    """Score (query, excerpt) pairs with the cross-encoder, squashed to 0-1 via sigmoid."""
    if not excerpts:
        return []
    reranker = get_reranker()
    logits = reranker.predict([(query, doc) for doc in excerpts], show_progress_bar=False)
    return [round(1.0 / (1.0 + math.exp(-float(l))), 4) for l in logits]
