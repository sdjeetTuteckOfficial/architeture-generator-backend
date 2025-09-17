# In app/services/crud.py
from sqlalchemy.orm import Session
from uuid import UUID

from app.core import models as pydantic_models
from app.db import models as db_models

def create_thread(db: Session, thread_data: pydantic_models.ThreadCreate):
    db_thread = db_models.Thread(**thread_data.model_dump())
    db.add(db_thread)
    db.commit()
    db.refresh(db_thread)
    return db_thread

def get_thread(db: Session, thread_id: UUID):
    return db.query(db_models.Thread).filter(db_models.Thread.thread_id == thread_id).first()

def get_threads(db: Session, user_id: UUID, skip: int = 0, limit: int = 100):
    return db.query(db_models.Thread).filter(db_models.Thread.user_id == user_id).offset(skip).limit(limit).all()

def create_conversation(db: Session, thread_id: UUID, conversation_data: pydantic_models.ConversationCreate):
    db_conversation = db_models.Conversation(**conversation_data.model_dump())
    db.add(db_conversation)
    db.commit()
    db.refresh(db_conversation)

    # Update the thread's conversation_ids array
    thread = get_thread(db, thread_id)
    if thread:
        thread.conversation_ids.append(db_conversation.conversation_id)
        db.commit()
        db.refresh(thread)
    
    return db_conversation

def get_conversation(db: Session, conversation_id: UUID):
    return db.query(db_models.Conversation).filter(db_models.Conversation.conversation_id == conversation_id).first()

def get_conversations(db: Session, thread_id: UUID, skip: int = 0, limit: int = 100):
    return db.query(db_models.Conversation).filter(db_models.Conversation.thread_id == thread_id).offset(skip).limit(limit).all()