"""Qdrant-backed per-user personalization memory.

We embed user messages and store them in a single Qdrant collection, tagged by
`user_id` in the payload. At chat time we retrieve the most relevant past
snippets for that user and inject them into the system prompt — "personalization
is all you need". All operations are best-effort: if Qdrant is unavailable the
bot keeps working without personalization.
"""
from __future__ import annotations

import logging
import uuid

from qdrant_client import AsyncQdrantClient, models

from app.config import settings
from app.services.openai_service import embed_text

log = logging.getLogger(__name__)

COLLECTION = "user_memories"

_client: AsyncQdrantClient | None = None
_ready = False


def _get_client() -> AsyncQdrantClient:
    global _client
    if _client is None:
        _client = AsyncQdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
    return _client


async def init() -> None:
    """Create the collection (and payload index) if it does not exist."""
    global _ready
    try:
        client = _get_client()
        existing = {c.name for c in (await client.get_collections()).collections}
        if COLLECTION not in existing:
            await client.create_collection(
                collection_name=COLLECTION,
                vectors_config=models.VectorParams(
                    size=settings.embed_dim, distance=models.Distance.COSINE
                ),
            )
            await client.create_payload_index(
                collection_name=COLLECTION,
                field_name="user_id",
                field_schema=models.PayloadSchemaType.INTEGER,
            )
        _ready = True
        log.info("Qdrant ready (collection=%s).", COLLECTION)
    except Exception as e:  # noqa: BLE001
        _ready = False
        log.warning("Qdrant unavailable, personalization disabled: %s", e)


async def remember(user_id: int, text: str, *, conversation_id: int | None = None,
                   role: str = "user") -> str | None:
    """Embed and store a snippet of memory for a user. Returns the vector id."""
    if not _ready or not text.strip():
        return None
    try:
        vector = await embed_text(text)
        point_id = str(uuid.uuid4())
        await _get_client().upsert(
            collection_name=COLLECTION,
            wait=True,  # make the point immediately searchable
            points=[
                models.PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={
                        "user_id": user_id,
                        "conversation_id": conversation_id,
                        "role": role,
                        "text": text[:2000],
                    },
                )
            ],
        )
        return point_id
    except Exception as e:  # noqa: BLE001
        log.warning("Qdrant remember failed: %s", e)
        return None


async def recall(user_id: int, query: str, k: int | None = None) -> list[str]:
    """Return up to k personalization snippets most relevant to `query`."""
    if not _ready or not query.strip():
        return []
    k = k or settings.personalization_topk
    try:
        vector = await embed_text(query)
        hits = await _get_client().search(
            collection_name=COLLECTION,
            query_vector=vector,
            limit=k,
            query_filter=models.Filter(
                must=[models.FieldCondition(key="user_id", match=models.MatchValue(value=user_id))]
            ),
            score_threshold=0.2,
        )
        return [h.payload.get("text", "") for h in hits if h.payload]
    except Exception as e:  # noqa: BLE001
        log.warning("Qdrant recall failed: %s", e)
        return []


async def close() -> None:
    if _client is not None:
        await _client.close()
