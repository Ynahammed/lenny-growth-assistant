# Lenny Growth Assistant — backend API
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# libgomp1 is required by torch/scipy at runtime.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download embedding + reranking models at build time so the first
# request doesn't pay ~15s of model load inside the container.
RUN python -c "import os; os.environ.setdefault('USE_TF','0'); \
from sentence_transformers import SentenceTransformer, CrossEncoder; \
SentenceTransformer('BAAI/bge-small-en-v1.5'); \
CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')" || echo "WARN: model predownload failed; models will download at first use"

COPY app ./app
COPY pytest.ini .

# Models + corpus + vector store live here; mount a volume for warm starts.
ENV HF_HOME=/app/.cache/huggingface \
    TRANSCRIPTS_DIR=/app/app/ingestion/transcripts \
    CHROMA_PERSIST_DIRECTORY=/app/chroma_db
RUN mkdir -p /app/.cache/huggingface /app/chroma_db
VOLUME ["/app/.cache/huggingface", "/app/chroma_db"]

EXPOSE 8001
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
