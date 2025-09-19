import os
import aiosmtplib
from email.message import EmailMessage
from datetime import timedelta, datetime, timezone
import secrets
from passlib.context import CryptContext
from itsdangerous import URLSafeTimedSerializer as TimedSerializer
from itsdangerous.exc import BadSignature, SignatureExpired
from jose import jwt, JWTError

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    """Hashes a plain text password using bcrypt."""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain text password against a hashed one."""
    return pwd_context.verify(plain_password, hashed_password)

# OTP generation
def generate_otp() -> str:
    """Generates a random 6-digit OTP."""
    return str(secrets.randbelow(900000) + 100000)

# Email sending (re-added for completeness, as it's still used by other endpoints)
async def send_email(to_email: str, subject: str, body: str):
    """Sends an email using environment variables for credentials."""
    email_user = os.environ.get("EMAIL_USER")
    email_password = os.environ.get("EMAIL_PASSWORD")
    email_host = os.environ.get("EMAIL_HOST")
    email_port = int(os.environ.get("EMAIL_PORT", 587))
    
    if not all([email_user, email_password, email_host]):
        print("Missing one or more email environment variables.")
        return False
        
    msg = EmailMessage()
    msg.set_content(body)
    msg["Subject"] = subject
    msg["From"] = email_user
    msg["To"] = to_email
    
    try:
        smtp = aiosmtplib.SMTP(hostname=email_host, port=email_port, use_tls=True)
        await smtp.connect()
        await smtp.login(email_user, email_password)
        await smtp.send_message(msg)
        await smtp.quit()
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False

# JWT Tokens
SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "your-default-secret-key")
ALGORITHM = "HS256"

def create_access_token(data: dict, expires_delta: timedelta = timedelta(hours=1)) -> str:
    """
    Creates a signed JWT access token.
    
    Args:
        data: Dictionary containing user data (must include "user_id").
        expires_delta: Token expiration time.
    
    Returns:
        Signed token string.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_token(token: str) -> dict | None:
    """
    Decodes a token and verifies its signature and expiration.
    
    Args:
        token: Token string to decode.
        
    Returns:
        Decoded token data or None if invalid/expired.
    """
    try:
        print(f"DEBUG: Attempting to decode token with SECRET_KEY: {SECRET_KEY[:10]}...")
        print(f"DEBUG: Token length: {len(token) if token else 0}")
        
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        print(f"DEBUG: Successfully decoded payload: {payload}")
        
        # Check if token is expired manually for debugging
        exp = payload.get('exp')
        if exp:
            exp_datetime = datetime.fromtimestamp(exp, tz=timezone.utc)
            now = datetime.now(timezone.utc)
            print(f"DEBUG: Token expires at: {exp_datetime}")
            print(f"DEBUG: Current time: {now}")
            print(f"DEBUG: Token expired: {now > exp_datetime}")
            
        return payload
    except JWTError as e:
        print(f"DEBUG: JWT decode error: {type(e).__name__}: {e}")
        return None
    except Exception as e:
        print(f"DEBUG: Unexpected decode error: {type(e).__name__}: {e}")
        return None
