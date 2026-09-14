"""
Chat and Session API Endpoints with SSE Streaming Support.
"""
import json
import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.database.db import get_db, SessionLocal
from app.database.models import SessionModel, MessageModel, ArtifactModel
from app.agents.agent_manager import AgentManager
from app.config import settings

logger = logging.getLogger("lenny_growth.routes.chat")
router = APIRouter(prefix="/api/chat", tags=["Chat & Sessions"])


class CreateSessionRequest(BaseModel):
    title: Optional[str] = "New Growth Conversation"
    provider: Optional[str] = None
    user_metadata: Optional[Dict[str, Any]] = None


class SendMessageRequest(BaseModel):
    content: str = Field(..., min_length=1, description="User prompt or question.")
    provider: Optional[str] = None
    guest: Optional[str] = None
    episode_number: Optional[int] = None


class SessionSummaryResponse(BaseModel):
    id: str
    title: str
    created_at: Optional[str]
    updated_at: Optional[str]
    provider_used: str
    message_count: int


class MessageDetailResponse(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    sources: List[Dict[str, Any]] = []
    timestamp: Optional[str]
    token_count: int = 0


class ArtifactDetailResponse(BaseModel):
    id: str
    session_id: str
    message_id: Optional[str]
    artifact_type: str
    title: str
    content: str
    created_at: Optional[str]


class SendMessageResponse(BaseModel):
    user_message: MessageDetailResponse
    assistant_message: MessageDetailResponse
    artifacts: List[ArtifactDetailResponse] = []
    follow_ups: List[str] = []


class SessionDetailResponse(BaseModel):
    id: str
    title: str
    created_at: Optional[str]
    updated_at: Optional[str]
    provider_used: str
    user_metadata: Dict[str, Any]
    messages: List[MessageDetailResponse]
    artifacts: List[ArtifactDetailResponse]


@router.get("/sessions", response_model=List[SessionSummaryResponse])
def list_sessions(db: Session = Depends(get_db)):
    sessions = db.query(SessionModel).order_by(SessionModel.updated_at.desc()).all()
    return [SessionSummaryResponse(**s.to_dict()) for s in sessions]


@router.post("/sessions", response_model=SessionDetailResponse, status_code=status.HTTP_201_CREATED)
def create_session(payload: CreateSessionRequest, db: Session = Depends(get_db)):
    provider_choice = payload.provider or settings.LLM_PROVIDER
    new_session = SessionModel(
        title=payload.title or "New Growth Conversation",
        provider_used=provider_choice,
        user_metadata=payload.user_metadata or {}
    )
    db.add(new_session)
    db.commit()
    db.refresh(new_session)
    logger.info(f"Created new chat session: {new_session.id} (Provider: {provider_choice})")
    
    return SessionDetailResponse(
        id=new_session.id,
        title=new_session.title,
        created_at=new_session.created_at.isoformat() if new_session.created_at else None,
        updated_at=new_session.updated_at.isoformat() if new_session.updated_at else None,
        provider_used=new_session.provider_used,
        user_metadata=new_session.user_metadata or {},
        messages=[],
        artifacts=[]
    )


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
def get_session(session_id: str, db: Session = Depends(get_db)):
    session_obj = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
        
    messages_out = [MessageDetailResponse(**m.to_dict()) for m in session_obj.messages]
    artifacts_out = [ArtifactDetailResponse(**a.to_dict()) for a in session_obj.artifacts]
    
    return SessionDetailResponse(
        id=session_obj.id,
        title=session_obj.title,
        created_at=session_obj.created_at.isoformat() if session_obj.created_at else None,
        updated_at=session_obj.updated_at.isoformat() if session_obj.updated_at else None,
        provider_used=session_obj.provider_used,
        user_metadata=session_obj.user_metadata or {},
        messages=messages_out,
        artifacts=artifacts_out
    )


@router.post("/sessions/{session_id}/messages", response_model=SendMessageResponse)
async def send_message(session_id: str, payload: SendMessageRequest, db: Session = Depends(get_db)):
    session_obj = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    user_msg = MessageModel(
        session_id=session_id,
        role="user",
        content=payload.content.strip()
    )
    db.add(user_msg)
    db.commit()
    db.refresh(user_msg)

    if session_obj.title == "New Growth Conversation" and len(session_obj.messages) <= 1:
        title_cand = payload.content.strip().split("\n")[0][:48]
        session_obj.title = title_cand
        db.commit()

    prior_messages = (
        db.query(MessageModel)
        .filter(MessageModel.session_id == session_id)
        .order_by(MessageModel.timestamp.asc())
        .all()
    )
    history_payload = [
        {"role": m.role, "content": m.content}
        for m in prior_messages[:-1]
    ]

    active_provider = payload.provider or session_obj.provider_used or settings.LLM_PROVIDER
    agent = AgentManager(provider_type=active_provider)

    retrieve_filters = {
        k: v for k, v in {
            "guest": payload.guest,
            "episode_number": payload.episode_number,
        }.items() if v is not None
    }
    turn_result = await agent.execute_turn(
        conversation_history=history_payload,
        user_message=payload.content,
        retrieve_filters=retrieve_filters or None,
    )

    asst_msg = MessageModel(
        session_id=session_id,
        role="assistant",
        content=turn_result.get("content", ""),
        sources=turn_result.get("sources", [])
    )
    db.add(asst_msg)
    db.commit()
    db.refresh(asst_msg)

    saved_artifacts = []
    for art in turn_result.get("artifacts", []):
        art_model = ArtifactModel(
            session_id=session_id,
            message_id=asst_msg.id,
            artifact_type=art.get("artifact_type", "markdown"),
            title=art.get("title", "Growth Artifact"),
            content=art.get("content", "")
        )
        db.add(art_model)
        db.commit()
        db.refresh(art_model)
        saved_artifacts.append(ArtifactDetailResponse(**art_model.to_dict()))

    return SendMessageResponse(
        user_message=MessageDetailResponse(**user_msg.to_dict()),
        assistant_message=MessageDetailResponse(**asst_msg.to_dict()),
        artifacts=saved_artifacts,
        follow_ups=turn_result.get("follow_ups", [])
    )


@router.post("/sessions/{session_id}/messages/stream")
async def send_message_stream(session_id: str, payload: SendMessageRequest):
    """Server-Sent Events (SSE) endpoint for real-time word-by-word streaming generation."""
    db = SessionLocal()
    try:
        session_obj = db.query(SessionModel).filter(SessionModel.id == session_id).first()
        if not session_obj:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

        user_msg = MessageModel(
            session_id=session_id,
            role="user",
            content=payload.content.strip()
        )
        db.add(user_msg)
        db.commit()
        db.refresh(user_msg)

        if session_obj.title == "New Growth Conversation" and len(session_obj.messages) <= 1:
            session_obj.title = payload.content.strip().split("\n")[0][:48]
            db.commit()

        prior_messages = (
            db.query(MessageModel)
            .filter(MessageModel.session_id == session_id)
            .order_by(MessageModel.timestamp.asc())
            .all()
        )
        history_payload = [
            {"role": m.role, "content": m.content}
            for m in prior_messages[:-1]
        ]
        active_provider = payload.provider or session_obj.provider_used or settings.LLM_PROVIDER
        retrieve_filters = {
            k: v for k, v in {
                "guest": payload.guest,
                "episode_number": payload.episode_number,
            }.items() if v is not None
        }
    finally:
        db.close()

    async def event_generator():
        agent = AgentManager(provider_type=active_provider)
        final_text = ""
        final_sources = []
        final_artifacts = []
        final_follow_ups = []

        try:
            async for event in agent.execute_turn_stream(
                conversation_history=history_payload,
                user_message=payload.content,
                retrieve_filters=retrieve_filters or None,
            ):
                if event.get("type") == "token":
                    final_text += event.get("token", "")
                elif event.get("type") == "sources":
                    final_sources = event.get("sources", [])
                elif event.get("type") == "artifacts":
                    final_artifacts = event.get("artifacts", [])
                elif event.get("type") == "done":
                    final_text = event.get("full_content", final_text)
                    final_sources = event.get("sources", final_sources)
                    final_artifacts = event.get("artifacts", final_artifacts)
                    final_follow_ups = event.get("follow_ups", [])

                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            logger.error(f"Streaming error in SSE: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            return

        # Save assistant message and artifacts to DB on completion
        db_write = SessionLocal()
        try:
            asst_msg = MessageModel(
                session_id=session_id,
                role="assistant",
                content=final_text,
                sources=final_sources
            )
            db_write.add(asst_msg)
            db_write.commit()
            db_write.refresh(asst_msg)

            saved_artifacts = []
            for art in final_artifacts:
                art_model = ArtifactModel(
                    session_id=session_id,
                    message_id=asst_msg.id,
                    artifact_type=art.get("artifact_type", "markdown"),
                    title=art.get("title", "Growth Artifact"),
                    content=art.get("content", "")
                )
                db_write.add(art_model)
                db_write.commit()
                db_write.refresh(art_model)
                saved_artifacts.append(art_model.to_dict())

            yield f"data: {json.dumps({'type': 'saved', 'message_id': asst_msg.id, 'artifacts': saved_artifacts, 'follow_ups': final_follow_ups})}\n\n"
        finally:
            db_write.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(session_id: str, db: Session = Depends(get_db)):
    session_obj = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    db.delete(session_obj)
    db.commit()
    logger.info(f"Deleted session: {session_id}")
    return None


@router.delete("/sessions", status_code=status.HTTP_204_NO_CONTENT)
def delete_all_sessions(db: Session = Depends(get_db)):
    """Bulk-delete every conversation (cascades to messages and artifacts)."""
    deleted = db.query(SessionModel).delete(synchronize_session=False)
    db.commit()
    logger.info(f"Deleted all sessions: {deleted} conversations removed")
    return None
