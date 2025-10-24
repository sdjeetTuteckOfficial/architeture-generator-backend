# app/api/dependencies.py
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
import uuid
from app.utils import decode_token
from app.database import get_db, SessionLocal
from app.models import User
from sqlalchemy.orm import Session

# Security scheme for token authentication
security = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """
    Dependency to get the current authenticated user from JWT token.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        # Extract token from credentials
        token = credentials.credentials
        print(f"DEBUG: Received token: {token[:20]}..." if token else "No token")
        
        # Decode the token - the `decode_token` function handles expiration.
        payload = decode_token(token)
        print(f"DEBUG: Decoded payload: {payload}")
        
        if payload is None:
            print("DEBUG: Payload is None - token decode failed")
            raise credentials_exception
            
        # Extract user_id from 'sub' claim
        user_id = payload.get("sub")
        print(f"DEBUG: Extracted user_id: {user_id}")
        if user_id is None:
            print("DEBUG: No 'sub' claim found in payload")
            print(f"DEBUG: Available keys: {list(payload.keys())}")
            raise credentials_exception
            
        # Convert string UUID to UUID object
        try:
            user_uuid = uuid.UUID(user_id)
            print(f"DEBUG: Converted to UUID: {user_uuid}")
        except ValueError as e:
            print(f"DEBUG: UUID conversion failed: {e}")
            raise credentials_exception
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"DEBUG: Unexpected error: {type(e).__name__}: {e}")
        raise credentials_exception
    
    # Get user from database
    try:
        user = db.query(User).filter(User.id == user_uuid).first()
        print(f"DEBUG: Database query result: {'User found' if user else 'User not found'}")
        if user:
            print(f"DEBUG: User active status: {user.is_active}")
    except Exception as e:
        print(f"DEBUG: Database query error: {e}")
        raise credentials_exception
        
    if user is None:
        print("DEBUG: User not found in database")
        raise credentials_exception
        
    # Check if user is active
    if not user.is_active:
        print("DEBUG: User is inactive")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Inactive user"
        )
    
    print("DEBUG: Authentication successful")
    return user


async def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """
    Ensures the retrieved user is active (this is a redundant check
    but kept for clarity).
    """
    return current_user


# ============================================================================
# NEW FUNCTION FOR WEBSOCKET AUTHENTICATION
# ============================================================================

async def get_current_user_from_websocket(token: str, db: Session) -> Optional[User]:
    """
    Validate JWT token for WebSocket connections.
    Returns User object if valid, None otherwise.
    
    This function is similar to get_current_user but designed for WebSocket
    connections where we can't use FastAPI's dependency injection system.
    
    Args:
        token: JWT token string
        db: Database session
        
    Returns:
        User object if authentication successful, None otherwise
    """
    try:
        print(f"[WebSocket Auth] Received token: {token[:20]}..." if token else "No token")
        
        # Decode the token using your existing utility function
        payload = decode_token(token)
        print(f"[WebSocket Auth] Decoded payload: {payload}")
        
        if payload is None:
            print("[WebSocket Auth] Payload is None - token decode failed")
            return None
            
        # Extract user_id from 'sub' claim
        user_id = payload.get("sub")
        print(f"[WebSocket Auth] Extracted user_id: {user_id}")
        
        if user_id is None:
            print("[WebSocket Auth] No 'sub' claim found in payload")
            print(f"[WebSocket Auth] Available keys: {list(payload.keys())}")
            return None
            
        # Convert string UUID to UUID object
        try:
            user_uuid = uuid.UUID(user_id)
            print(f"[WebSocket Auth] Converted to UUID: {user_uuid}")
        except ValueError as e:
            print(f"[WebSocket Auth] UUID conversion failed: {e}")
            return None
        
        # Query user from database
        try:
            user = db.query(User).filter(User.id == user_uuid).first()
            print(f"[WebSocket Auth] Database query result: {'User found' if user else 'User not found'}")
            
            if user:
                print(f"[WebSocket Auth] User ID: {user.id}")
                print(f"[WebSocket Auth] User email: {user.email}")
                print(f"[WebSocket Auth] User active: {user.is_active}")
                
        except Exception as e:
            print(f"[WebSocket Auth] Database query error: {e}")
            return None
            
        # Check if user exists and is active
        if user is None:
            print("[WebSocket Auth] User not found in database")
            return None
            
        if not user.is_active:
            print("[WebSocket Auth] User is inactive")
            return None
        
        print("[WebSocket Auth] Authentication successful!")
        return user
        
    except Exception as e:
        print(f"[WebSocket Auth] Unexpected error: {type(e).__name__}: {e}")
        import traceback
        print(f"[WebSocket Auth] Traceback: {traceback.format_exc()}")
        return None


# ============================================================================
# OPTIONAL: Token validation helper for WebSocket
# ============================================================================

def validate_websocket_token(token: str) -> bool:
    """
    Quick token validation without database lookup.
    Useful for initial WebSocket handshake validation.
    
    Args:
        token: JWT token string
        
    Returns:
        True if token is valid (not expired, proper format), False otherwise
    """
    try:
        payload = decode_token(token)
        if payload is None:
            return False
            
        # Check if required claims exist
        if "sub" not in payload:
            return False
            
        return True
        
    except Exception as e:
        print(f"[Token Validation] Error: {e}")
        return False