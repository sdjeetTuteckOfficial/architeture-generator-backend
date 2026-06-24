from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime


class UserBase(BaseModel):
    id: Optional[str] = None
    email: EmailStr
    is_active: bool = False
    first_name: Optional[str] = None
    last_name: Optional[str] = None

    class Config:
        from_attributes = True


class UserCreateResponse(BaseModel):
    id: Optional[str] = None
    email: EmailStr
    is_active: bool = False
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    otp: Optional[str] = None
    message: Optional[str] = None

    class Config:
        from_attributes = True


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class OtpVerify(BaseModel):
    email: EmailStr
    otp: str


class EmailRequest(BaseModel):
    email: EmailStr


class PasswordReset(BaseModel):
    email: EmailStr
    otp: str
    new_password: str

    class Config:
        json_schema_extra = {
            "example": {
                "email": "user@example.com",
                "otp": "123456",
                "new_password": "newpassword123",
            }
        }


class Token(BaseModel):
    access_token: str
    token_type: str


class MessageResponse(BaseModel):
    message: str


class OtpResponse(BaseModel):
    message: str
    otp: Optional[str] = None
