"""Migrate existing sessions/messages/artifacts from SQLite to PostgreSQL.

Reads every row from the SQLite file (default: backend/lenny_growth.db),
recreates it in the Postgres database at DATABASE_URL, and skips rows whose
primary key already exists there — so it is safe to run more than once.

Usage (from backend/):
    python scripts/migrate_sqlite_to_postgres.py
    python scripts/migrate_sqlite_to_postgres.py --sqlite lenny_growth.db --truncate
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.config import settings  # noqa: E402
from app.database.db import DATABASE_URL, _normalize_database_url  # noqa: E402
from app.database.models import ArtifactModel, Base, MessageModel, SessionModel  # noqa: E402

DEFAULT_SQLITE = Path(__file__).resolve().parent.parent / "lenny_growth.db"


def main() -> int:
    parser = argparse.ArgumentParser(description="SQLite -> PostgreSQL migration")
    parser.add_argument("--sqlite", default=str(DEFAULT_SQLITE), help="Path to the SQLite file")
    parser.add_argument(
        "--truncate",
        action="store_true",
        help="Delete existing Postgres rows first (fresh import)",
    )
    args = parser.parse_args()

    if not Path(args.sqlite).exists():
        print(f"No SQLite file at {args.sqlite} — nothing to migrate.")
        return 0

    sqlite_engine = create_engine(f"sqlite:///{args.sqlite}")
    src = sessionmaker(bind=sqlite_engine)()

    dest_engine = create_engine(_normalize_database_url(DATABASE_URL))
    Base.metadata.create_all(dest_engine)
    dst = sessionmaker(bind=dest_engine)()

    if args.truncate:
        n = dst.query(ArtifactModel).delete()
        m = dst.query(MessageModel).delete()
        s = dst.query(SessionModel).delete()
        dst.commit()
        print(f"Truncated Postgres tables ({s} sessions, {m} messages, {n} artifacts).")

    existing_session_ids = {row[0] for row in dst.query(SessionModel.id).all()}

    counts = {"sessions": 0, "messages": 0, "artifacts": 0}
    skipped = 0
    orphans = {"messages": 0, "artifacts": 0}

    for s in src.query(SessionModel).all():
        if s.id in existing_session_ids:
            skipped += 1
            continue
        dst.add(SessionModel(
            id=s.id, title=s.title, created_at=s.created_at, updated_at=s.updated_at,
            provider_used=s.provider_used if s.provider_used != "anthropic" else "ollama",
            user_metadata=s.user_metadata,
        ))
        counts["sessions"] += 1

    # SQLite does not enforce FKs by default, so source rows may reference
    # sessions that no longer exist (orphaned by historic deletes). Only
    # migrate children whose parent made it across.
    migrated_session_ids = {s.id for s in src.query(SessionModel).all()} - existing_session_ids

    for m in src.query(MessageModel).all():
        if m.session_id in existing_session_ids:
            continue
        if m.session_id not in migrated_session_ids:
            orphans["messages"] += 1
            continue
        dst.add(MessageModel(
            id=m.id, session_id=m.session_id, role=m.role, content=m.content,
            sources=m.sources, timestamp=m.timestamp, token_count=m.token_count,
        ))
        counts["messages"] += 1

    for a in src.query(ArtifactModel).all():
        if a.session_id in existing_session_ids:
            continue
        if a.session_id not in migrated_session_ids:
            orphans["artifacts"] += 1
            continue
        dst.add(ArtifactModel(
            id=a.id, session_id=a.session_id, message_id=a.message_id,
            artifact_type=a.artifact_type, title=a.title, content=a.content,
            created_at=a.created_at,
        ))
        counts["artifacts"] += 1

    dst.commit()
    dst.close()
    src.close()

    print(f"Migrated {counts['sessions']} sessions, {counts['messages']} messages, "
          f"{counts['artifacts']} artifacts to {_normalize_database_url(DATABASE_URL)}.")
    if skipped:
        print(f"Skipped {skipped} sessions already present in Postgres.")
    if any(orphans.values()):
        print(f"Skipped orphaned rows (no parent session in SQLite): "
              f"{orphans['messages']} messages, {orphans['artifacts']} artifacts.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
