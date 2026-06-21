"""Models package.

Tables are split across modules by domain (one script per related group of
tables). Importing this package registers every model on ``Base.metadata`` —
which is what Alembic's autogenerate and the rest of the app rely on.
"""
from app.models.conversation import Conversation
from app.models.group import Group, GroupMessage
from app.models.message import Message
from app.models.model_selection import ModelSelection
from app.models.system import BroadcastLog, Migration
from app.models.token_audit import TokenAudit
from app.models.user import User, UserEmojiStat, UserMemory, UserTag
from app.models.web import WebSearch

__all__ = [
    "User",
    "UserTag",
    "UserMemory",
    "UserEmojiStat",
    "Conversation",
    "Message",
    "ModelSelection",
    "TokenAudit",
    "Group",
    "GroupMessage",
    "WebSearch",
    "BroadcastLog",
    "Migration",
]
