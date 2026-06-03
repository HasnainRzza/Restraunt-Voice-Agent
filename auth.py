import os
import jwt
import random
import bcrypt
from datetime import datetime, timedelta, timezone

JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-restaurant-jwt-token-key-change-in-prod")
JWT_ALGORITHM = "HS256"

def hash_password(password: str) -> str:
    """Return the hashed password using bcrypt directly."""
    # Convert password to bytes
    password_bytes = password.encode('utf-8')
    # Generate salt and hash
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against its hash using bcrypt directly."""
    try:
        plain_bytes = plain_password.encode('utf-8')
        hashed_bytes = hashed_password.encode('utf-8')
        return bcrypt.checkpw(plain_bytes, hashed_bytes)
    except Exception:
        return False

def generate_jwt(email: str, expires_in_minutes: int = 60) -> str:
    """Generate a JWT token for the user."""
    payload = {
        "sub": email,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=expires_in_minutes)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def verify_jwt(token: str) -> str:
    """Verify a JWT token and return the email if valid, or None."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload.get("sub")
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None

def generate_otp() -> tuple[str, str]:
    """Generate a 6-digit OTP and its expiration timestamp (5 mins from now)."""
    otp = f"{random.randint(100000, 999999)}"
    # Store expiry as ISO timestamp in UTC
    expiry = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    return otp, expiry

def is_otp_valid(stored_otp: str, stored_expiry: str, provided_otp: str) -> bool:
    """Verify if the provided OTP matches and has not expired."""
    if not stored_otp or not stored_expiry:
        return False
    if provided_otp != stored_otp:
        return False
    try:
        expiry_dt = datetime.fromisoformat(stored_expiry)
        return datetime.now(timezone.utc) < expiry_dt
    except ValueError:
        return False
