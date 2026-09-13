from fastapi import APIRouter, Depends, HTTPException

from app import db
from app.auth import require_api
from app.models import KeywordSetIn, KeywordSetPatch
from app.scrapers import ALL_SOURCES

router = APIRouter(prefix="/keyword-sets", tags=["keyword sets"], dependencies=[Depends(require_api)])


@router.get("")
def list_sets():
    return db.list_all(db.KEYWORD_SETS)


@router.get("/sources")
def sources():
    return {"available_sources": ALL_SOURCES}


@router.post("", status_code=201)
def create_set(body: KeywordSetIn):
    if db.list_all(db.KEYWORD_SETS, name=body.name):
        raise HTTPException(409, "name already exists")
    unknown = [s for s in body.sources if s not in ALL_SOURCES]
    if unknown:
        raise HTTPException(422, f"unknown sources: {unknown}")
    doc_id = db.upsert(db.KEYWORD_SETS, None, {**body.model_dump(), "created_at": db.now()})
    return db.get(db.KEYWORD_SETS, doc_id)


@router.get("/{set_id}")
def get_set(set_id: str):
    ks = db.get(db.KEYWORD_SETS, set_id)
    if not ks:
        raise HTTPException(404)
    return ks


@router.patch("/{set_id}")
def patch_set(set_id: str, body: KeywordSetPatch):
    if not db.get(db.KEYWORD_SETS, set_id):
        raise HTTPException(404)
    db.upsert(db.KEYWORD_SETS, set_id, body.model_dump(exclude_none=True))
    return db.get(db.KEYWORD_SETS, set_id)


@router.delete("/{set_id}", status_code=204)
def delete_set(set_id: str):
    db.delete(db.KEYWORD_SETS, set_id)
