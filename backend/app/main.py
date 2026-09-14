"""
FastAPI Entry Point for Lenny Growth Assistant.
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import text

from app.config import settings
from app.database.db import init_db, engine
from app.routes.chat import router as chat_router
from app.routes.artifacts import router as artifacts_router
from app.llm.provider import get_provider
from app.llm.telemetry import telemetry
from app.ingestion.ingest import get_collection_stats, run_ingestion
from app.middleware.error_handlers import (
    validation_exception_handler,
    database_exception_handler,
    connection_exception_handler,
    general_exception_handler,
)
from app.middleware.logging_middleware import StructuredLoggingMiddleware

# Configure root logger
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("lenny_growth.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle manager."""
    logger.info("Starting Lenny Growth Assistant Backend...")
    
    # 1. Initialize DB tables
    init_db()
    
    # 2. Verify Vector Store & auto-ingest if empty or updated
    stats = get_collection_stats()
    if stats.get("status") != "active" or stats.get("total_chunks", 0) < 40:
        logger.info("ChromaDB collection needs indexing. Running automated ingestion...")
        try:
            run_ingestion()
            logger.info("Transcript ingestion finished successfully.")
        except Exception as e:
            logger.error(f"Automatic ingestion failed on startup: {e}", exc_info=True)
    else:
        logger.info(f"ChromaDB ready: {stats.get('total_chunks')} transcript chunks available.")

    # 3. Log active provider status
    provider = get_provider()
    provider_health = await provider.check_health()
    logger.info(f"Active LLM Provider: {provider.provider_name} ({provider_health.get('status')})")

    yield

    logger.info("Shutting down Lenny Growth Assistant Backend...")


app = FastAPI(
    title=settings.APP_NAME,
    description="Conversational Growth Assistant grounded in Lenny's Podcast Transcripts with Multi-Agent PM Tools and Ship30 Skills.",
    version="2.0.0",
    lifespan=lifespan
)

# Middleware
app.add_middleware(StructuredLoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Error Handlers
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(SQLAlchemyError, database_exception_handler)
app.add_exception_handler(ConnectionError, connection_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)

# Routers
app.include_router(chat_router)
app.include_router(artifacts_router)


@app.get("/api/health", tags=["System"])
async def health_check():
    """Health check verifying database, vector store, and active LLM provider."""
    db_status = "healthy"
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"unhealthy: {e}"

    vector_stats = get_collection_stats()
    provider = get_provider()
    provider_health = await provider.check_health()

    return {
        "status": "online",
        "app_name": settings.APP_NAME,
        "environment": settings.ENVIRONMENT,
        "database": db_status,
        "vector_store": vector_stats,
        "llm_provider": provider_health,
        "llm_telemetry": telemetry.snapshot()
    }


@app.get("/api/config", tags=["System"])
def get_public_config():
    """Public configuration exposed to frontend UI."""
    return {
        "active_provider": settings.LLM_PROVIDER,
        "available_providers": [
            {
                "id": "ollama",
                "label": "Ollama (Local Llama 3.2)",
                "description": f"Private offline model on {settings.OLLAMA_BASE_URL}",
                "requires_api_key": False,
                "configured": True
            },
            {
                "id": "groq",
                "label": "Groq Cloud (GPT-OSS 120B)",
                "description": "Ultra-fast sub-second cloud inference (500+ tok/s)",
                "requires_api_key": True,
                "configured": bool(settings.GROQ_API_KEY)
            },
            {
                "id": "gemini",
                "label": "Google Gemini 3.6",
                "description": "Google AI Cloud model",
                "requires_api_key": True,
                "configured": bool(settings.GEMINI_API_KEY)
            },
            {
                "id": "mock",
                "label": "Instant Mock Engine",
                "description": "Instant transcript engine for zero-setup local testing",
                "requires_api_key": False,
                "configured": True
            }
        ],
        "ollama_base_url": settings.OLLAMA_BASE_URL
    }


@app.get("/api/corpus", tags=["System"])
def get_corpus_metadata():
    """Guests and episodes available in the indexed transcript corpus,
    for building retrieval filter chips in the UI."""
    try:
        from app.ingestion.ingest import get_chroma_client, ensure_compatible_collection
        client = get_chroma_client()
        collection, _ = ensure_compatible_collection(client)
        count = collection.count()
        if count == 0:
            return {"guests": [], "episodes": [], "total_chunks": 0}
        metas = collection.get(include=["metadatas"]).get("metadatas", [])

        by_episode = {}
        for m in metas:
            ep = int(m.get("episode_number") or 0)
            entry = by_episode.setdefault(ep, {
                "episode_number": ep,
                "episode_title": m.get("episode_title", "Unknown"),
                "guest": m.get("guest", "Unknown"),
            })

        episodes = sorted(by_episode.values(), key=lambda e: e["episode_number"])
        guests = sorted({e["guest"] for e in episodes})
        return {"guests": guests, "episodes": episodes, "total_chunks": count}
    except Exception as e:
        logger.error(f"Error building corpus metadata: {e}", exc_info=True)
        return {"guests": [], "episodes": [], "total_chunks": 0, "error": str(e)}
