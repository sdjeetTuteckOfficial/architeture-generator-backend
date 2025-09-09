from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime

# Base schema for User (for responses)
class UserBase(BaseModel):
    id: Optional[str] = None
    email: EmailStr
    is_active: bool = False
    first_name: Optional[str] = None
    last_name: Optional[str] = None

    class Config:
        from_attributes = True

# Schema for user registration response (includes OTP)
class UserCreateResponse(BaseModel):
    id: Optional[str] = None
    email: EmailStr
    is_active: bool = False
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    otp: Optional[str] = None  # Include OTP in response

    class Config:
        from_attributes = True

# Schema for user creation (signup)
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    first_name: Optional[str] = None  # Make optional
    last_name: Optional[str] = None   # Make optional

# Schema for user login (signin) - only email and password
class UserLogin(BaseModel):
    email: EmailStr
    password: str

# Schema for OTP verification
class OtpVerify(BaseModel):
    email: EmailStr
    otp: str

# Schema for email requests (resend OTP, forgot password)
class EmailRequest(BaseModel):
    email: EmailStr

# Schema for password reset
class PasswordReset(BaseModel):
    email: EmailStr
    otp: str
    new_password: str

    class Config:
        json_schema_extra = {
            "example": {
                "email": "user@example.com",
                "otp": "123456",
                "new_password": "newpassword123"
            }
        }

# Schema for JWT token response
class Token(BaseModel):
    access_token: str
    token_type: str

# Schema for success messages
class MessageResponse(BaseModel):
    message: str

# Schema for OTP response (includes OTP for development)
class OtpResponse(BaseModel):
    message: str
    otp: Optional[str] = None