from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone

from .. import models, schemas, utils
from ..database import get_db
from ..utils import (
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

# -----------------
# User Registration
# -----------------
@router.post("/signup", response_model=schemas.UserCreateResponse, status_code=status.HTTP_201_CREATED)
async def signup(user: schemas.UserCreate, db: Session = Depends(get_db)):
    """
    Register a new user and return a verification OTP in the response.
    """
    # Check if user already exists
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # Generate OTP and hash password
    otp = generate_otp()
    hashed_password = hash_password(user.password)

    db_user = models.User(
        email=user.email,
        hashed_password=hashed_password,
        otp_secret=otp,
        otp_created_at=datetime.now(timezone.utc),
        first_name=getattr(user, 'first_name', None),  # Optional
        last_name=getattr(user, 'last_name', None)     # Optional
    )

    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    # ✅ Return OTP in response instead of sending email
    return {
        "id": str(db_user.id),
        "email": db_user.email,
        "is_active": db_user.is_active,
        "first_name": db_user.first_name,
        "last_name": db_user.last_name,
        "otp": otp  # OTP included directly
    }

# @router.post("/signup", response_model=schemas.UserCreateResponse, status_code=status.HTTP_201_CREATED)
# async def signup(user: schemas.UserCreate, db: Session = Depends(get_db)):
#     """
#     Register a new user and send a verification OTP to their email.
#     """
#     db_user = db.query(models.User).filter(models.User.email == user.email).first()
#     if db_user:
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail="Email already registered"
#         )

#     otp = generate_otp()
#     hashed_password = hash_password(user.password)

#     db_user = models.User(
#         email=user.email,
#         hashed_password=hashed_password,
#         otp_secret=otp,
#         otp_created_at=datetime.now(timezone.utc),
#         first_name=getattr(user, 'first_name', None),  # Optional field
#         last_name=getattr(user, 'last_name', None)     # Optional field
#     )

#     db.add(db_user)
#     db.commit()
#     db.refresh(db_user)

#     # Send OTP email
#     subject = "Verify Your Email"
#     body = f"Your one-time password (OTP) is: {otp}"
#     if not await send_email(user.email, subject, body):
#         # Handle email sending failure
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail="Could not send verification email"
#         )
        
#     # Return user data with OTP
#     return {
#         "id": str(db_user.id),
#         "email": db_user.email,
#         "is_active": db_user.is_active,
#         "first_name": db_user.first_name,
#         "last_name": db_user.last_name,
#         "otp": otp  # Include OTP in response
#     }

# -----------------
# OTP Verification
# -----------------
@router.post("/verify-otp", response_model=schemas.MessageResponse, status_code=status.HTTP_200_OK)
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

    # Ensure otp_created_at is timezone-aware
    if user.otp_created_at.tzinfo is None:
        otp_created_at = user.otp_created_at.replace(tzinfo=timezone.utc)
    else:
        otp_created_at = user.otp_created_at

    otp_valid_until = otp_created_at + timedelta(minutes=5)
    now_utc = datetime.now(timezone.utc)

    if user.otp_secret == otp_data.otp and now_utc < otp_valid_until:
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
# Resend OTP
# -----------------
@router.post("/resend-otp", response_model=schemas.OtpResponse, status_code=status.HTTP_200_OK)
async def resend_otp(email_data: schemas.EmailRequest, db: Session = Depends(get_db)):
    """
    Resend OTP to user's email for account verification.
    """
    user = db.query(models.User).filter(models.User.email == email_data.email).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    if user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Account is already verified"
        )
    
    # Generate new OTP
    otp = generate_otp()
    user.otp_secret = otp
    user.otp_created_at = datetime.now(timezone.utc)
    
    db.commit()
    
    # Send OTP email
    subject = "Verify Your Email - New OTP"
    body = f"Your new one-time password (OTP) is: {otp}"
    if not await send_email(email_data.email, subject, body):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not send verification email"
        )
    
    return {"message": "OTP has been resent to your email", "otp": otp}

# -----------------
# Forgot Password
# -----------------

# -----------------
# Forgot Password
# -----------------
@router.post("/forgot-password", response_model=schemas.OtpResponse, status_code=status.HTTP_200_OK)
async def forgot_password(email_data: schemas.EmailRequest, db: Session = Depends(get_db)):
    """
    Generate a password reset OTP and return it in the response (no email sent).
    """
    user = db.query(models.User).filter(models.User.email == email_data.email).first()
    
    if not user:
        # Don't reveal existence, return None for security
        return {"message": "If the email exists, a password reset OTP has been generated", "otp": None}
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please verify your email first"
        )
    
    # Generate password reset OTP
    otp = generate_otp()
    user.otp_secret = otp
    user.otp_created_at = datetime.now(timezone.utc)
    
    db.commit()
    
    # ✅ Return OTP directly in response
    return {
        "message": "Password reset OTP has been generated",
        "otp": otp
    }

# @router.post("/forgot-password", response_model=schemas.OtpResponse, status_code=status.HTTP_200_OK)
# async def forgot_password(email_data: schemas.EmailRequest, db: Session = Depends(get_db)):
#     """
#     Send password reset OTP to user's email.
#     """
#     user = db.query(models.User).filter(models.User.email == email_data.email).first()
    
#     if not user:
#         # Don't reveal if email exists or not for security, but don't send OTP
#         return {"message": "If the email exists, a password reset OTP has been sent", "otp": None}
    
#     if not user.is_active:
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail="Please verify your email first"
#         )
    
#     # Generate password reset OTP
#     otp = generate_otp()
#     user.otp_secret = otp
#     user.otp_created_at = datetime.now(timezone.utc)
    
#     db.commit()
    
#     # Send password reset email
#     subject = "Password Reset Request"
#     body = f"Your password reset OTP is: {otp}. This OTP will expire in 5 minutes."
#     if not await send_email(email_data.email, subject, body):
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail="Could not send password reset email"
#         )
    
#     return {"message": "Password reset OTP has been sent to your email", "otp": otp}

# -----------------
# Reset Password
# -----------------
@router.post("/reset-password", response_model=schemas.MessageResponse, status_code=status.HTTP_200_OK)
def reset_password(reset_data: schemas.PasswordReset, db: Session = Depends(get_db)):
    """
    Reset user's password using OTP verification.
    """
    user = db.query(models.User).filter(models.User.email == reset_data.email).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please verify your email first"
        )
    
    # Ensure otp_created_at is timezone-aware
    if user.otp_created_at.tzinfo is None:
        otp_created_at = user.otp_created_at.replace(tzinfo=timezone.utc)
    else:
        otp_created_at = user.otp_created_at

    otp_valid_until = otp_created_at + timedelta(minutes=5)
    now_utc = datetime.now(timezone.utc)

    if user.otp_secret != reset_data.otp or now_utc >= otp_valid_until:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OTP"
        )
    
    # Reset password
    user.hashed_password = hash_password(reset_data.new_password)
    user.otp_secret = None  # Invalidate OTP after use
    
    db.commit()
    
    return {"message": "Password has been reset successfully"}

# -----------------
# User Sign-in
# -----------------
@router.post("/signin", response_model=schemas.Token)
def signin(user: schemas.UserLogin, db: Session = Depends(get_db)):
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