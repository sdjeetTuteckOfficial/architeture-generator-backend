# In app/database/models.py
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from sqlalchemy import ARRAY

from app.database import Base

class Thread(Base):
    __tablename__ = 'threads'
    
    thread_id = Column(UUID(as_uuid=True), primary_key=True, default=func.gen_random_uuid())
    user_id = Column(UUID(as_uuid=True), nullable=False)
    thread_name = Column(String(255), nullable=False)
    conversation_ids = Column(ARRAY(UUID(as_uuid=True)), nullable=False, default=[])
    created_at = Column(DateTime(timezone=True), server_default=func.now())  # Add this column

    conversations = relationship("Conversation", back_populates="thread")

class Conversation(Base):
    __tablename__ = 'conversations'

    conversation_id = Column(UUID(as_uuid=True), primary_key=True, default=func.gen_random_uuid())
    thread_id = Column(UUID(as_uuid=True), ForeignKey('threads.thread_id'), nullable=False)
    version = Column(Integer, nullable=False)
    diagram_json = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    thread = relationship("Thread", back_populates="conversations")