import os
import aiosmtplib
from email.message import EmailMessage
from datetime import timedelta, datetime, timezone
import secrets
from passlib.context import CryptContext
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


async def send_email(to_email: str, subject: str, body: str):
    """
    Sends an email using environment variables for credentials.
    Set BYPASS_SMTP=true to skip external email delivery and let signup proceed.
    """
    bypass_smtp = os.environ.get("BYPASS_SMTP", "true").lower() in ("1", "true", "yes", "on")
    if bypass_smtp:
        print(f"SMTP bypass enabled. Skipping email send to {to_email}.")
        return True

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
        if email_port == 587:
            smtp = aiosmtplib.SMTP(
                hostname=email_host,
                port=email_port,
                start_tls=False,
                use_tls=False,
            )
            await smtp.connect()
            await smtp.starttls()
            await smtp.login(email_user, email_password)
        elif email_port == 465:
            smtp = aiosmtplib.SMTP(
                hostname=email_host,
                port=email_port,
                use_tls=True,
            )
            await smtp.connect()
            await smtp.login(email_user, email_password)
        else:
            smtp = aiosmtplib.SMTP(hostname=email_host, port=email_port)
            await smtp.connect()
            await smtp.login(email_user, email_password)

        await smtp.send_message(msg)
        await smtp.quit()
        print(f"Email sent successfully to {to_email}")
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False


async def send_email_gmail_alternative(to_email: str, subject: str, body: str):
    """
    Alternative Gmail-specific email function.
    Kept for compatibility with older code paths.
    """
    bypass_smtp = os.environ.get("BYPASS_SMTP", "true").lower() in ("1", "true", "yes", "on")
    if bypass_smtp:
        print(f"SMTP bypass enabled. Skipping Gmail send to {to_email}.")
        return True

    email_user = os.environ.get("EMAIL_USER")
    email_password = os.environ.get("EMAIL_PASSWORD")

    if not all([email_user, email_password]):
        print("Missing Gmail credentials.")
        return False

    msg = EmailMessage()
    msg.set_content(body)
    msg["Subject"] = subject
    msg["From"] = email_user
    msg["To"] = to_email

    try:
        import ssl

        context = ssl.create_default_context()
        smtp = aiosmtplib.SMTP(
            hostname="smtp.gmail.com",
            port=587,
            tls_context=context,
            start_tls=True,
        )

        await smtp.connect()
        await smtp.login(email_user, email_password)
        await smtp.send_message(msg)
        await smtp.quit()
        print(f"Gmail email sent successfully to {to_email}")
        return True
    except Exception as e:
        print(f"Gmail alternative method failed: {e}")
        return False


# JWT Tokens
SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "your-default-secret-key")
ALGORITHM = "HS256"


def create_access_token(data: dict, expires_delta: timedelta = timedelta(hours=1)) -> str:
    """
    Creates a signed JWT access token.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_token(token: str) -> dict | None:
    """
    Decodes a token and verifies its signature and expiration.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None
    except Exception:
        return None
