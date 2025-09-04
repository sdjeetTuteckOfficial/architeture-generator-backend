from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
import os

from . import models, schemas, utils
from .database import get_db
from .utils import (
    hash_password,
    verify_password,
    generate_otp,
    send_email,
    create_access_token
)

router = APIRouter()

# -----------------
# User Registration
# -----------------
@router.post("/signup", response_model=schemas.UserBase, status_code=status.HTTP_201_CREATED)
async def signup(user: schemas.UserCreate, db: Session = Depends(get_db)):
    """
    Register a new user and send a verification OTP to their email.
    """
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    otp = generate_otp()
    hashed_password = hash_password(user.password)
    
    db_user = models.User(
        email=user.email,
        hashed_password=hashed_password,
        otp_secret=otp,
        otp_created_at=datetime.now(timezone.utc)
    )
    
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    # Send OTP email
    subject = "Verify Your Email"
    body = f"Your one-time password (OTP) is: {otp}"
    if not await send_email(user.email, subject, body):
        # Handle email sending failure
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not send verification email"
        )
        
    return db_user

# -----------------
# OTP Verification
# -----------------
@router.post("/verify-otp", status_code=status.HTTP_200_OK)
def verify_otp(otp_data: schemas.OtpVerify, db: Session = Depends(get_db)):
    """
    Verify the user's OTP to activate their account.
    """
    user = db.query(models.User).filter(models.User.email == otp_data.email).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
        
    # Check if OTP is correct and not expired (e.g., within 5 minutes)
    otp_valid_until = user.otp_created_at + timedelta(minutes=5)
    
    # Use a timezone-aware 'now' object for comparison
    now_utc_aware = datetime.now(timezone.utc)

    if user.otp_secret == otp_data.otp and now_utc_aware < otp_valid_until:
        user.is_active = True
        user.otp_secret = None  # Invalidate OTP after use
        db.commit()
        return {"message": "Email successfully verified!"}
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OTP"
        )

# -----------------
# User Sign-in
# -----------------
@router.post("/signin", response_model=schemas.Token)
def signin(user: schemas.UserCreate, db: Session = Depends(get_db)):
    """
    Sign in an active user and return a JWT access token.
    """
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    
    if not db_user or not verify_password(user.password, db_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )
        
    if not db_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email first"
        )
    
    access_token = create_access_token(data={"sub": db_user.email})
    
    return {"access_token": access_token, "token_type": "bearer"}
