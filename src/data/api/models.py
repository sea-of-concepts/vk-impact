"""Pydantic data models for VK API entities."""
from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field


class VKUser(BaseModel):
    """VK User profile model."""
    id: int
    first_name: str = ""
    last_name: str = ""
    photo_50: Optional[str] = None
    photo_100: Optional[str] = None
    photo_200: Optional[str] = None
    photo_max_orig: Optional[str] = None
    online: int = 0
    online_mobile: Optional[int] = 0
    online_app: Optional[int] = None
    last_seen: Optional[Dict[str, Any]] = None
    status: Optional[str] = ""
    domain: Optional[str] = ""
    can_write_private_message: Optional[int] = 1

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def avatar_url(self) -> str:
        return self.photo_200 or self.photo_100 or self.photo_50 or ""


class VKGroup(BaseModel):
    """VK Community / Group profile model."""
    id: int
    name: str = ""
    screen_name: Optional[str] = ""
    is_closed: int = 0
    type: str = "group"
    photo_50: Optional[str] = None
    photo_100: Optional[str] = None
    photo_200: Optional[str] = None

    @property
    def avatar_url(self) -> str:
        return self.photo_200 or self.photo_100 or self.photo_50 or ""


class VKAttachment(BaseModel):
    """VK Message or Wall post attachment."""
    type: str
    photo: Optional[Dict[str, Any]] = None
    audio: Optional[Dict[str, Any]] = None
    doc: Optional[Dict[str, Any]] = None
    video: Optional[Dict[str, Any]] = None
    sticker: Optional[Dict[str, Any]] = None
    link: Optional[Dict[str, Any]] = None
    wall: Optional[Dict[str, Any]] = None


class VKMessage(BaseModel):
    """VK Private Message model."""
    id: int = 0
    date: int = 0
    peer_id: int
    from_id: int
    sender_name: str = ""
    sender_avatar: str = ""
    text: str = ""
    out: int = 0
    conversation_message_id: Optional[int] = 0
    attachments: Any = Field(default_factory=list)
    fwd_messages: Any = Field(default_factory=list)
    reply_message: Optional[Dict[str, Any]] = None
    random_id: Optional[int] = 0
    important: bool = False
    is_hidden: bool = False
    is_read: bool = True  # Computed helper

    @property
    def is_outgoing(self) -> bool:
        return bool(self.out)


class VKConversation(BaseModel):
    """VK Conversation object within conversations list."""
    peer: Dict[str, Any]
    last_message_id: int = 0
    in_read: int = 0
    out_read: int = 0
    unread_count: int = 0
    important: bool = False
    unanswered: bool = False
    chat_settings: Optional[Dict[str, Any]] = None

    @property
    def peer_id(self) -> int:
        return self.peer.get("id", 0)

    @property
    def peer_type(self) -> str:
        return self.peer.get("type", "user")


class VKDialogItem(BaseModel):
    """Aggregated dialog item for rendering in DialogsScreen list."""
    peer_id: int
    title: str = ""
    avatar_url: str = ""
    last_message_text: str = ""
    last_message_time: int = 0
    unread_count: int = 0
    is_online: bool = False
    is_outgoing: bool = False
    is_read: bool = True
    is_channel: bool = False
    is_pinned: bool = False
    is_archived: bool = False
    is_muted: bool = False


