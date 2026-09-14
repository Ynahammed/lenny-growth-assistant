#!/usr/bin/env python3
"""
Standalone Ingestion Script for Lenny Growth Assistant.
"""
import os
import sys
import argparse
import logging
from pathlib import Path
from typing import List, Dict, Any

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import chromadb
from chromadb.utils import embedding_functions
from app.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("lenny_growth.ingest")


def parse_transcript_file(file_path: Path) -> Dict[str, Any]:
    content = file_path.read_text(encoding="utf-8")
    
    metadata: Dict[str, Any] = {
        "source_file": file_path.name,
        "guest": "Unknown",
        "episode_title": file_path.stem.replace("_", " ").title(),
        "episode_number": 0,
        "topic_tags": "general"
    }
    
    body = content
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            header_lines = parts[1].strip().split("\n")
            body = parts[2].strip()
            
            for line in header_lines:
                if ":" in line:
                    key, val = line.split(":", 1)
                    key = key.strip().lower()
                    val = val.strip().strip("[]\"'")
                    if key == "guest":
                        metadata["guest"] = val
                    elif key == "episode_title":
                        metadata["episode_title"] = val
                    elif key == "episode_number":
                        try:
                            metadata["episode_number"] = int(val)
                        except ValueError:
                            metadata["episode_number"] = 0
                    elif key == "topic_tags":
                        metadata["topic_tags"] = val
    
    return {
        "metadata": metadata,
        "body": body
    }


def chunk_text(text: str, chunk_size: int = 600, overlap: int = 120) -> List[str]:
    paragraphs = text.split("\n\n")
    chunks: List[str] = []
    current_chunk = ""
    
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
            
        if len(current_chunk) + len(para) + 2 <= chunk_size:
            current_chunk = f"{current_chunk}\n\n{para}" if current_chunk else para
        else:
            if current_chunk:
                chunks.append(current_chunk)
                overlap_text = current_chunk[-overlap:] if len(current_chunk) > overlap else current_chunk
                current_chunk = f"{overlap_text}\n\n{para}"
            else:
                while len(para) > chunk_size:
                    chunks.append(para[:chunk_size])
                    para = para[chunk_size - overlap:]
                current_chunk = para
                
    if current_chunk:
        chunks.append(current_chunk)
        
    return chunks


def get_chroma_client(persist_dir: str = None) -> chromadb.ClientAPI:
    db_dir = persist_dir or settings.CHROMA_PERSIST_DIRECTORY
    os.makedirs(db_dir, exist_ok=True)
    return chromadb.PersistentClient(path=db_dir)


def run_ingestion(transcripts_dir: str = None, reset: bool = False) -> Dict[str, Any]:
    target_dir = Path(transcripts_dir or settings.TRANSCRIPTS_DIR)
    if not target_dir.exists():
        logger.error(f"Transcripts directory not found: {target_dir}")
        raise FileNotFoundError(f"Transcripts directory not found: {target_dir}")
        
    client = get_chroma_client()
    collection_name = settings.CHROMA_COLLECTION_NAME
    
    if reset:
        try:
            client.delete_collection(name=collection_name)
            logger.info(f"Deleted existing collection: {collection_name}")
        except Exception:
            pass
            
    embedding_fn = embedding_functions.DefaultEmbeddingFunction()
    collection = client.get_or_create_collection(
        name=collection_name,
        embedding_function=embedding_fn,
        metadata={"description": "Lenny's Podcast Transcript Vectors"}
    )
    
    files = list(target_dir.glob("*.txt")) + list(target_dir.glob("*.md"))
    if not files:
        logger.warning(f"No transcript files (.txt, .md) found in {target_dir}")
        return {"total_files": 0, "total_chunks": 0}
        
    total_chunks = 0
    all_documents = []
    all_metadatas = []
    all_ids = []
    
    logger.info(f"Starting ingestion of {len(files)} transcript files from {target_dir}...")
    
    for file_path in files:
        parsed = parse_transcript_file(file_path)
        base_meta = parsed["metadata"]
        body = parsed["body"]
        
        chunks = chunk_text(body, chunk_size=settings.CHUNK_SIZE, overlap=settings.CHUNK_OVERLAP)
        logger.info(f"Processed '{file_path.name}': {len(chunks)} chunks extracted (Guest: {base_meta['guest']})")
        
        for idx, chunk in enumerate(chunks):
            chunk_id = f"{file_path.stem}_chunk_{idx:03d}"
            chunk_metadata = {
                "source_file": base_meta["source_file"],
                "guest": str(base_meta["guest"]),
                "episode_title": str(base_meta["episode_title"]),
                "episode_number": int(base_meta["episode_number"]),
                "topic_tags": str(base_meta["topic_tags"]),
                "chunk_index": int(idx),
                "total_chunks": int(len(chunks)),
            }
            
            all_ids.append(chunk_id)
            all_documents.append(chunk)
            all_metadatas.append(chunk_metadata)
            total_chunks += 1
            
    if all_ids:
        batch_size = 100
        for i in range(0, len(all_ids), batch_size):
            collection.upsert(
                ids=all_ids[i:i+batch_size],
                documents=all_documents[i:i+batch_size],
                metadatas=all_metadatas[i:i+batch_size]
            )
            
    logger.info(f"Ingestion complete! Successfully indexed {total_chunks} chunks across {len(files)} files.")
    return {
        "total_files": len(files),
        "total_chunks": total_chunks,
        "collection_count": collection.count(),
        "persist_dir": settings.CHROMA_PERSIST_DIRECTORY
    }


def get_collection_stats() -> Dict[str, Any]:
    try:
        client = get_chroma_client()
        collection = client.get_collection(name=settings.CHROMA_COLLECTION_NAME)
        count = collection.count()
        return {
            "status": "active",
            "collection_name": settings.CHROMA_COLLECTION_NAME,
            "total_chunks": count,
            "persist_directory": settings.CHROMA_PERSIST_DIRECTORY
        }
    except Exception as e:
        return {
            "status": "empty_or_error",
            "error": str(e),
            "collection_name": settings.CHROMA_COLLECTION_NAME
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest Lenny's Podcast Transcripts into ChromaDB.")
    parser.add_argument("--reset", action="store_true", help="Delete and recreate vector collection.")
    parser.add_argument("--stats", action="store_true", help="Print vector store collection statistics.")
    parser.add_argument("--dir", type=str, default=None, help="Custom transcripts directory path.")
    
    args = parser.parse_args()
    
    if args.stats:
        stats = get_collection_stats()
        print(f"\n--- ChromaDB Collection Stats ---")
        for k, v in stats.items():
            print(f"{k}: {v}")
    else:
        results = run_ingestion(transcripts_dir=args.dir, reset=args.reset)
        print(f"\n--- Ingestion Results ---")
        for k, v in results.items():
            print(f"{k}: {v}")
