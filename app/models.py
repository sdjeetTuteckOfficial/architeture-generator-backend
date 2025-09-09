import uuid
from sqlalchemy import Column, String, Boolean, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from .database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=False)
    otp_secret = Column(String, nullable=True)
    otp_created_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # New fields
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)
