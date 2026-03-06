"""Message model for tracking LinkedIn messages sent/received."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class MessageDirection(str, enum.Enum):
    OUTBOUND = "outbound"
    INBOUND = "inbound"


class MessageType(str, enum.Enum):
    CONNECTION_NOTE = "connection_note"
    FIRST_MESSAGE = "first_message"
    FOLLOWUP = "followup"
    REPLY = "reply"
    OBJECTION_HANDLE = "objection_handle"


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True, index=True
    )

    direction: Mapped[MessageDirection] = mapped_column(Enum(MessageDirection), nullable=False)
    message_type: Mapped[MessageType] = mapped_column(Enum(MessageType), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # LLM-generated metadata
    llm_prompt_used: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_model_used: Mapped[str | None] = mapped_column(Text, nullable=True)

    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    lead = relationship("Lead", back_populates="messages")
    conversation = relationship("Conversation", back_populates="messages")
