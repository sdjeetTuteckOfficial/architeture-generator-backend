import os
import aiosmtplib
from email.message import EmailMessage
from datetime import datetime, timedelta
import secrets
from passlib.context import CryptContext
# The correct class to import from itsdangerous is TimedSerializer.
# The original code imported this correctly but used the wrong name.
from itsdangerous import TimedSerializer
from itsdangerous.exc import BadSignature, SignatureExpired

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

# Email sending
async def send_email(to_email: str, subject: str, body: str):
    """Sends an email using environment variables for credentials."""
    # Use .get() with a default to avoid errors if env variables are missing
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
# It is recommended to have a fallback value in case the env var is not set.
SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "your-default-secret-key")
# Fix: The expires_in argument is not part of the TimedSerializer constructor.
# It should be passed to the dumps() method.
serializer = TimedSerializer(SECRET_KEY)

def create_access_token(data: dict) -> str:
    """Creates a JWT access token with a timed expiration."""
    # Corrected line: pass expires_in to the dumps method
    return serializer.dumps(data, expires_in=timedelta(hours=1)).decode('utf-8')

def decode_token(token: str) -> dict | None:
    """Decodes a JWT token and handles expiration or invalid signature."""
    try:
        return serializer.loads(token)
    except (BadSignature, SignatureExpired):
        return None
