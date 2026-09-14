"""Tests for transcript ingestion and chunking."""
from pathlib import Path

import pytest

from app.config import settings
from app.ingestion.ingest import (
    parse_transcript_file,
    chunk_text,
    run_ingestion,
    get_collection_stats,
)


class TestParseTranscriptFile:
    def test_parses_frontmatter_metadata(self, tmp_path):
        f = tmp_path / "guest_x_topic.txt"
        f.write_text(
            "---\n"
            "guest: Jane Doe\n"
            "episode_title: The Growth Episode\n"
            "episode_number: 42\n"
            "topic_tags: growth, loops\n"
            "---\n"
            "Body paragraph one.\n\n"
            "Body paragraph two."
        )
        parsed = parse_transcript_file(f)
        assert parsed["metadata"]["guest"] == "Jane Doe"
        assert parsed["metadata"]["episode_number"] == 42
        assert parsed["metadata"]["episode_title"] == "The Growth Episode"
        assert "paragraph two" in parsed["body"]
        assert parsed["body"].startswith("Body paragraph one")

    def test_file_without_frontmatter_uses_defaults(self, tmp_path):
        f = tmp_path / "plain_name_file.txt"
        f.write_text("Just some content here.")
        parsed = parse_transcript_file(f)
        assert parsed["metadata"]["guest"] == "Unknown"
        assert parsed["metadata"]["episode_number"] == 0
        assert parsed["metadata"]["episode_title"] == "Plain Name File"


class TestChunkText:
    def test_small_text_single_chunk(self):
        assert chunk_text("hello world", chunk_size=600, overlap=120) == ["hello world"]

    def test_respects_chunk_size(self):
        para = "word " * 300  # ~1500 chars
        chunks = chunk_text(para.strip(), chunk_size=600, overlap=120)
        assert all(len(c) <= 650 for c in chunks)
        assert len(chunks) >= 2

    def test_overlap_carries_context(self):
        para1 = "A" * 500
        para2 = "B" * 200
        chunks = chunk_text(f"{para1}\n\n{para2}", chunk_size=600, overlap=120)
        assert len(chunks) >= 2
        # Second chunk should carry tail of the first (overlap)
        assert chunks[1].startswith("A" * 50) or "B" in chunks[1]


class TestIngestion:
    @pytest.fixture(scope="class")
    def ingestion_result(self):
        return run_ingestion(reset=True)

    def test_ingests_real_corpus(self, ingestion_result):
        assert ingestion_result["total_files"] == 10
        assert ingestion_result["total_chunks"] > 40

    def test_collection_stats_after_ingestion(self, ingestion_result):
        stats = get_collection_stats()
        assert stats["status"] == "active"
        assert stats["total_chunks"] == ingestion_result["total_chunks"]

    def test_missing_directory_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            run_ingestion(transcripts_dir=str(tmp_path / "nope"))
