"""
RAG Retrieval Tool for querying Lenny's Podcast Vector Store.
"""
import logging
from typing import Dict, Any, List
import chromadb
from chromadb.utils import embedding_functions
from app.config import settings

logger = logging.getLogger("lenny_growth.tools.retrieve")

RETRIEVE_TOOL_SCHEMA = {
    "name": "retrieve",
    "description": "Searches the vector database for relevant transcripts from Lenny's Podcast on product management, growth loops, marketplace metrics, and strategy.",
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
            }
        },
        "required": ["query"]
    }
}


def execute_retrieve(query: str, top_k: int = 4) -> Dict[str, Any]:
    try:
        client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIRECTORY)
        embedding_fn = embedding_functions.DefaultEmbeddingFunction()
        
        try:
            collection = client.get_collection(
                name=settings.CHROMA_COLLECTION_NAME,
                embedding_function=embedding_fn
            )
        except Exception:
            logger.warning("Vector collection not found. Running auto-ingestion...")
            from app.ingestion.ingest import run_ingestion
            run_ingestion()
            collection = client.get_collection(
                name=settings.CHROMA_COLLECTION_NAME,
                embedding_function=embedding_fn
            )

        results = collection.query(
            query_texts=[query],
            n_results=top_k,
            include=["documents", "metadatas", "distances"]
        )

        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]
        ids = results.get("ids", [[]])[0]

        chunks: List[Dict[str, Any]] = []
        for i, doc in enumerate(documents):
            meta = metadatas[i] if i < len(metadatas) else {}
            dist = distances[i] if i < len(distances) else 1.0
            score = round(max(0.0, 1.0 - (dist / 2.0)), 3)
            
            chunks.append({
                "chunk_id": ids[i] if i < len(ids) else f"chunk_{i}",
                "guest": meta.get("guest", "Unknown"),
                "episode_title": meta.get("episode_title", "Unknown"),
                "episode_number": meta.get("episode_number", 0),
                "topic_tags": meta.get("topic_tags", ""),
                "source_file": meta.get("source_file", ""),
                "excerpt": doc,
                "relevance_score": score
            })

        logger.info(f"Retrieved {len(chunks)} chunks for query: '{query}'")
        return {
            "query": query,
            "chunk_count": len(chunks),
            "chunks": chunks
        }
    except Exception as e:
        logger.error(f"Error during retrieve tool execution: {e}", exc_info=True)
        return {
            "query": query,
            "chunk_count": 0,
            "chunks": [],
            "error": str(e)
        }
