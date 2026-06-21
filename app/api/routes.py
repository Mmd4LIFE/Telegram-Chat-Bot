"""Lightweight JSON API."""
from fastapi import APIRouter

from app import __version__
from app.database import SessionLocal
from app.services import crud

router = APIRouter(prefix="/api")


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/version")
async def version():
    return {"version": __version__}


@router.get("/stats")
async def stats():
    async with SessionLocal() as session:
        return await crud.get_stats(session)
