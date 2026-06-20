"""Lightweight JSON API."""
from fastapi import APIRouter

from app.database import SessionLocal
from app.services import crud

router = APIRouter(prefix="/api")


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/stats")
async def stats():
    async with SessionLocal() as session:
        return await crud.get_stats(session)
