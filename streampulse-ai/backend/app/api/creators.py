import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db import get_db
from app.models import Creator, Stream
from app.schemas.api import CreatorIn, CreatorOut, CreatorUpdate
from app.services.audit import audit

router = APIRouter(prefix="/api/creators", tags=["creators"], dependencies=[Depends(current_user)])


@router.post("", response_model=CreatorOut, status_code=201)
def create(body: CreatorIn, db: Session = Depends(get_db)):
    data = body.model_dump()
    data["profile_image"] = str(body.profile_image) if body.profile_image else None
    creator = Creator(**data)
    db.add(creator)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "a creator with this YouTube channel already exists") from exc
    # attach existing streams of the same channel
    if creator.youtube_channel_id:
        db.query(Stream).filter(Stream.youtube_channel_id == creator.youtube_channel_id,
                                Stream.creator_id.is_(None)).update({Stream.creator_id: creator.id})
    audit(db, "creator.created", creator_id=str(creator.id), name=creator.name, authorised=creator.authorised)
    db.commit()
    return creator


@router.get("", response_model=list[CreatorOut])
def list_(db: Session = Depends(get_db)):
    return db.query(Creator).order_by(Creator.name).all()


@router.patch("/{creator_id}", response_model=CreatorOut)
def update(creator_id: uuid.UUID, body: CreatorUpdate, db: Session = Depends(get_db)):
    creator = db.get(Creator, creator_id)
    if creator is None:
        raise HTTPException(404, "creator not found")
    data = body.model_dump(exclude_unset=True)
    if "profile_image" in data:
        data["profile_image"] = str(data["profile_image"]) if data["profile_image"] else None
    for k, v in data.items():
        setattr(creator, k, v)
    if creator.authorised and not (creator.authorisation_notes or "").strip():
        raise HTTPException(422, "authorisation_notes are required when marking a creator as authorised")
    audit(db, "creator.updated", creator_id=str(creator.id), changes=list(data))
    db.commit()
    return creator


@router.delete("/{creator_id}", status_code=204)
def delete(creator_id: uuid.UUID, db: Session = Depends(get_db)):
    creator = db.get(Creator, creator_id)
    if creator is None:
        raise HTTPException(404, "creator not found")
    audit(db, "creator.deleted", creator_id=str(creator.id), name=creator.name)
    db.delete(creator)
    db.commit()
