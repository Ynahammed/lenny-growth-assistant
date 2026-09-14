"""
Artifact Generation and Retrieval API Endpoints.
"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database.db import get_db
from app.database.models import ArtifactModel, MessageModel, SessionModel
from app.agents.tools.ship30_essay import execute_ship30_essay, SHIP30_SYSTEM_INSTRUCTIONS
from app.agents.tools.artifact_gen import execute_artifact_gen
from app.llm.provider import get_provider
from app.config import settings

logger = logging.getLogger("lenny_growth.routes.artifacts")
router = APIRouter(prefix="/api/artifacts", tags=["Artifacts"])


class GenerateArtifactRequest(BaseModel):
    session_id: str
    message_id: Optional[str] = None
    topic: str
    source_content: Optional[str] = None
    artifact_type: str = "essay"
    target_audience: Optional[str] = "Product Managers and Growth Leads"


class ArtifactResponse(BaseModel):
    id: str
    session_id: str
    message_id: Optional[str]
    artifact_type: str
    title: str
    content: str
    created_at: Optional[str]


@router.get("/{artifact_id}", response_model=ArtifactResponse)
def get_artifact(artifact_id: str, db: Session = Depends(get_db)):
    art = db.query(ArtifactModel).filter(ArtifactModel.id == artifact_id).first()
    if not art:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")
    return ArtifactResponse(**art.to_dict())


@router.post("/generate", response_model=ArtifactResponse, status_code=status.HTTP_201_CREATED)
async def generate_artifact(payload: GenerateArtifactRequest, db: Session = Depends(get_db)):
    session_obj = db.query(SessionModel).filter(SessionModel.id == payload.session_id).first()
    if not session_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    content_to_use = payload.source_content or ""
    if not content_to_use and payload.message_id:
        msg = db.query(MessageModel).filter(MessageModel.id == payload.message_id).first()
        if msg:
            content_to_use = msg.content

    if not content_to_use:
        content_to_use = f"Insights on {payload.topic} from Lenny's Podcast."

    provider = get_provider(session_obj.provider_used or settings.LLM_PROVIDER)
    
    if payload.artifact_type == "essay":
        system_instruction = SHIP30_SYSTEM_INSTRUCTIONS
        prompt = (
            f"Generate a Ship30 Atomic Essay on: {payload.topic}\n\n"
            f"Target Audience: {payload.target_audience}\n\n"
            f"Source Evidence:\n{content_to_use}\n"
        )
        res = await provider.generate(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=system_instruction
        )
        essay_content = res.content.strip()
        
        title = f"Ship30: {payload.topic}"
        for line in essay_content.split("\n"):
            if line.startswith("# "):
                title = line.replace("# ", "").strip()
                break

        art_record = ArtifactModel(
            session_id=payload.session_id,
            message_id=payload.message_id,
            artifact_type="essay",
            title=title,
            content=essay_content
        )
    elif payload.artifact_type == "html":
        art_data = execute_artifact_gen(
            title=payload.topic,
            artifact_type="html",
            content=f"<div class='card'><h3>Executive Framework</h3><p>{content_to_use}</p></div>"
        )
        art_record = ArtifactModel(
            session_id=payload.session_id,
            message_id=payload.message_id,
            artifact_type="html",
            title=art_data["title"],
            content=art_data["content"]
        )
    else:
        art_record = ArtifactModel(
            session_id=payload.session_id,
            message_id=payload.message_id,
            artifact_type="markdown",
            title=payload.topic,
            content=content_to_use
        )

    db.add(art_record)
    db.commit()
    db.refresh(art_record)
    
    logger.info(f"Generated artifact {art_record.id} ({art_record.artifact_type}) for session {payload.session_id}")
    return ArtifactResponse(**art_record.to_dict())
