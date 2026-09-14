"""
RAG Retrieval Tool for querying Lenny's Podcast Vector Store.

Pipeline: optional guest/episode metadata filter -> bi-encoder candidate search
(bge-small) -> cosine gate (RELEVANCE_CUTOFF) -> cross-encoder rerank
(ms-marco MiniLM) -> top_k. Off-topic queries produce an explicit
no_relevant_evidence result instead of forced nearest neighbors.
"""
import logging
from typing import Dict, Any, List, Optional
import chromadb
from app.config import settings
from app.rag.embeddings import embed_texts, rerank_pairs

logger = logging.getLogger("lenny_growth.tools.retrieve")

RETRIEVE_TOOL_SCHEMA = {
    "name": "retrieve",
    "description": "Searches the vector database for relevant transcripts from Lenny's Podcast on product management, growth loops, marketplace metrics, and strategy. Supports optional filters to restrict the search to a specific guest or episode.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The specific question or semantic search term to look up in the transcript library."
            },
            "top_k": {
                "type": "integer",
                "description": "Number of top relevant transcript chunks to return (default 4).",
                "default": 4
            },
            "guest": {
                "type": "string",
                "description": "Optional: restrict the search to episodes with this guest (e.g. 'Shreyas Doshi', 'Casey Winters'). Use when the user names a guest or asks 'only X episodes'."
            },
            "episode_number": {
                "type": "integer",
                "description": "Optional: restrict the search to one episode number (e.g. 42). Use when the user references a specific episode."
            }
        },
        "required": ["query"]
    }
}


def get_available_guests() -> List[str]:
    """Distinct guest names in the indexed corpus (for the UI filter picker)."""
    try:
        client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIRECTORY)
        from app.ingestion.ingest import ensure_compatible_collection
        collection, _ = ensure_compatible_collection(client)
        if collection.count() == 0:
            return []
        metas = collection.get(include=["metadatas"]).get("metadatas", [])
        return sorted({m.get("guest", "") for m in metas if m.get("guest")})
    except Exception as e:
        logger.error(f"Error listing guests: {e}")
        return []


def _resolve_filter(
    collection,
    guest: Optional[str],
    episode_number: Optional[int],
) -> Optional[Dict[str, Any]]:
    """Build a Chroma where-clause from free-form guest/episode inputs.

    Guest names are matched fuzzily case-insensitively against the indexed
    metadata (e.g. 'shreyas' -> 'Shreyas Doshi'); unknown guests raise
    ValueError listing the available ones so the LLM can self-correct."""
    if not guest and episode_number is None:
        return None

    conditions = []

    if guest:
        wanted = str(guest).strip().lower()
        metas = collection.get(include=["metadatas"]).get("metadatas", [])
        indexed_guests = {m.get("guest", "") for m in metas if m.get("guest")}
        matches = {g for g in indexed_guests
                   if wanted == g.lower() or wanted in g.lower() or g.lower() in wanted}
        if not matches:
            raise ValueError(
                f"Guest '{guest}' not found in the corpus. Available guests: "
                f"{sorted(indexed_guests)}"
            )
        if len(matches) == 1:
            conditions.append({"guest": {"$eq": next(iter(matches))}})
        else:
            conditions.append({"guest": {"$in": sorted(matches)}})

    if episode_number is not None:
        conditions.append({"episode_number": {"$eq": int(episode_number)}})

    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


def execute_retrieve(
    query: str,
    top_k: int = 4,
    relevance_cutoff: float = None,
    guest: Optional[str] = None,
    episode_number: Optional[int] = None,
) -> Dict[str, Any]:
    """Retrieve transcript chunks for a query.

    Pipeline: metadata filter (guest/episode) -> bi-encoder candidates ->
    cosine gate (topical admission / refusal, RELEVANCE_CUTOFF) -> cross-encoder
    rerank (ordering) -> top_k. The gate runs on cosine because cross-encoders
    measure answer-bearing relevance and would wrongly refuse topically-relevant
    dialogue excerpts; the reranker then surfaces chunks that answer the
    question."""
    if relevance_cutoff is None:
        relevance_cutoff = settings.RELEVANCE_CUTOFF
    try:
        client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIRECTORY)

        try:
            from app.ingestion.ingest import ensure_compatible_collection
            collection, _ = ensure_compatible_collection(client)
        except ImportError:
            # Fallback for exotic deploy layouts without the ingestion module.
            from chromadb.utils import embedding_functions
            collection = client.get_collection(
                name=settings.CHROMA_COLLECTION_NAME,
                embedding_function=embedding_functions.DefaultEmbeddingFunction(),
            )

        if collection.count() == 0:
            logger.warning("Vector collection empty. Running auto-ingestion...")
            from app.ingestion.ingest import run_ingestion, ensure_compatible_collection as _ensure
            run_ingestion()
            collection, _ = _ensure(client)

        where = _resolve_filter(collection, guest, episode_number)

        # Over-fetch a candidate pool for the reranker to reorder.
        n_results = top_k
        if settings.RERANK_ENABLED:
            n_results = max(top_k, settings.RERANK_CANDIDATES)
        n_results = max(1, min(n_results, collection.count()))
        if n_results == 0:
            return {"query": query, "chunk_count": 0, "chunks": [], "no_relevant_evidence": True}

        query_embedding = embed_texts([query], is_query=True)[0]
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"]
        )

        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]
        ids = results.get("ids", [[]])[0]

        candidates: List[Dict[str, Any]] = []
        for i, doc in enumerate(documents):
            meta = metadatas[i] if i < len(metadatas) else {}
            dist = distances[i] if i < len(distances) else 1.0
            # Chroma l2 space with normalized vectors: 1 - l2^2/2 == cosine similarity.
            bi_score = round(max(0.0, 1.0 - (dist / 2.0)), 4)
            candidates.append({
                "chunk_id": ids[i] if i < len(ids) else f"chunk_{i}",
                "guest": meta.get("guest", "Unknown"),
                "episode_title": meta.get("episode_title", "Unknown"),
                "episode_number": meta.get("episode_number", 0),
                "topic_tags": meta.get("topic_tags", ""),
                "source_file": meta.get("source_file", ""),
                "excerpt": doc,
                "retrieval_score": bi_score,
            })

        if not candidates:
            result: Dict[str, Any] = {
                "query": query,
                "chunk_count": 0,
                "chunks": [],
            }
            if where is not None:
                result["error"] = (
                    "No indexed chunks match the requested guest/episode filter."
                )
            else:
                result["no_relevant_evidence"] = True
            return result

        # Gate on bi-encoder cosine: topical admission / refusal.
        gate_passed: List[Dict[str, Any]] = []
        dropped = 0
        for c in candidates:
            if c["retrieval_score"] < relevance_cutoff:
                dropped += 1
                continue
            gate_passed.append(c)

        # Order gate-passing chunks by cross-encoder relevance.
        if gate_passed and settings.RERANK_ENABLED:
            rerank_scores = rerank_pairs(query, [c["excerpt"] for c in gate_passed])
            for c, rs in zip(gate_passed, rerank_scores):
                c["relevance_score"] = rs
            gate_passed.sort(key=lambda c: c["relevance_score"], reverse=True)
        else:
            for c in gate_passed:
                c["relevance_score"] = c["retrieval_score"]

        chunks = gate_passed[:top_k]

        if dropped:
            logger.info(
                f"Dropped {dropped}/{len(candidates)} chunks below cosine gate "
                f"{relevance_cutoff} for query: '{query}'"
            )

        out: Dict[str, Any] = {
            "query": query,
            "chunk_count": len(chunks),
            "chunks": chunks
        }
        if dropped and not chunks:
            out["no_relevant_evidence"] = True
        if where is not None:
            out["filtered"] = {
                k: v for k, v in {"guest": guest, "episode_number": episode_number}.items()
                if v is not None
            }
        return out
    except ValueError as e:
        # Unknown guest/episode: a filter the LLM can correct on its next call.
        logger.info(f"Filter resolution failed for query '{query}': {e}")
        return {
            "query": query,
            "chunk_count": 0,
            "chunks": [],
            "filter_error": str(e),
        }
    except Exception as e:
        logger.error(f"Error during retrieve tool execution: {e}", exc_info=True)
        return {
            "query": query,
            "chunk_count": 0,
            "chunks": [],
            "error": str(e)
        }
