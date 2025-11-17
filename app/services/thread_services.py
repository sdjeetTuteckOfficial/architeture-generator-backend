# app/services/thread_services.py
from sqlalchemy.orm import Session
from uuid import UUID
from typing import List, Optional

from app.core import models as pydantic_models
from app.db import models as db_models


def create_thread(db: Session, thread_data: pydantic_models.ThreadCreate) -> db_models.Thread:
    """Create a new thread"""
    db_thread = db_models.Thread(
        user_id=thread_data.user_id,
        thread_name=thread_data.thread_name,
        conversation_ids=[]  # Initialize empty array
    )
    db.add(db_thread)
    db.commit()
    db.refresh(db_thread)
    return db_thread


def get_thread(db: Session, thread_id: UUID) -> Optional[db_models.Thread]:
    """Get a thread by ID"""
    return db.query(db_models.Thread).filter(
        db_models.Thread.thread_id == thread_id
    ).first()


def get_threads(db: Session, user_id: UUID, skip: int = 0, limit: int = 100) -> List[db_models.Thread]:
    """Get all threads for a user"""
    return (
        db.query(db_models.Thread)
        .filter(db_models.Thread.user_id == user_id)
        .order_by(db_models.Thread.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def update_thread(db: Session, thread_id: UUID, thread_name: str) -> Optional[db_models.Thread]:
    """Update thread name"""
    thread = get_thread(db, thread_id)
    if thread:
        thread.thread_name = thread_name
        db.commit()
        db.refresh(thread)
    return thread


def delete_thread(db: Session, thread_id: UUID) -> bool:
    """Delete a thread and all its conversations"""
    thread = get_thread(db, thread_id)
    if thread:
        # Delete all conversations first
        db.query(db_models.Conversation).filter(
            db_models.Conversation.thread_id == thread_id
        ).delete()
        
        # Delete thread
        db.delete(thread)
        db.commit()
        return True
    return False


def create_conversation(
    db: Session, 
    thread_id: UUID, 
    conversation_data: pydantic_models.ConversationCreate
) -> db_models.Conversation:
    """Create a new conversation in a thread"""
    
    # Verify thread exists
    thread = get_thread(db, thread_id)
    if not thread:
        raise ValueError(f"Thread {thread_id} not found")
    
    # Create conversation
    db_conversation = db_models.Conversation(
        thread_id=conversation_data.thread_id,
        version=conversation_data.version,
        diagram_json=conversation_data.diagram_json
    )
    db.add(db_conversation)
    db.commit()
    db.refresh(db_conversation)
    
    # Update thread's conversation_ids array
    if db_conversation.conversation_id not in thread.conversation_ids:
        thread.conversation_ids = thread.conversation_ids + [db_conversation.conversation_id]
        db.commit()
        db.refresh(thread)
    
    return db_conversation


def get_conversation(db: Session, conversation_id: UUID) -> Optional[db_models.Conversation]:
    """Get a conversation by ID"""
    return db.query(db_models.Conversation).filter(
        db_models.Conversation.conversation_id == conversation_id
    ).first()


def get_conversations(
    db: Session, 
    thread_id: UUID, 
    skip: int = 0, 
    limit: int = 100
) -> List[db_models.Conversation]:
    """Get all conversations in a thread"""
    return (
        db.query(db_models.Conversation)
        .filter(db_models.Conversation.thread_id == thread_id)
        .order_by(db_models.Conversation.version.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_latest_conversation(db: Session, thread_id: UUID) -> Optional[db_models.Conversation]:
    """Get the most recent conversation in a thread"""
    return (
        db.query(db_models.Conversation)
        .filter(db_models.Conversation.thread_id == thread_id)
        .order_by(db_models.Conversation.version.desc())
        .first()
    )


def get_conversation_by_version(
    db: Session, 
    thread_id: UUID, 
    version: int
) -> Optional[db_models.Conversation]:
    """Get a specific version of conversation"""
    return (
        db.query(db_models.Conversation)
        .filter(
            db_models.Conversation.thread_id == thread_id,
            db_models.Conversation.version == version
        )
        .first()
    )


def delete_conversation(db: Session, conversation_id: UUID) -> bool:
    """Delete a specific conversation"""
    conversation = get_conversation(db, conversation_id)
    if conversation:
        thread_id = conversation.thread_id
        
        # Remove from thread's conversation_ids
        thread = get_thread(db, thread_id)
        if thread and conversation_id in thread.conversation_ids:
            thread.conversation_ids = [
                cid for cid in thread.conversation_ids 
                if cid != conversation_id
            ]
            db.commit()
        
        # Delete conversation
        db.delete(conversation)
        db.commit()
        return True
    return False

def update_conversation(
    db: Session, 
    conversation_id: UUID, 
    version: Optional[int] = None, 
    diagram_json: Optional[str] = None
) -> Optional[db_models.Conversation]:
    """Update conversation version or diagram JSON"""
    conversation = get_conversation(db, conversation_id)
    
    if conversation:
        # Check and update version
        if version is not None:
            conversation.version = version
            
        # Check and update diagram_json
        if diagram_json is not None:
            conversation.diagram_json = diagram_json
            
        # Only commit if changes were made (though SQLAlchemy often tracks this)
        if version is not None or diagram_json is not None:
            db.commit()
            db.refresh(conversation)
            
    return conversation