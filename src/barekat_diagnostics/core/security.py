"""Security: JWT and password hashing."""

from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from barekat_diagnostics.core.config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
  return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
  return pwd_context.verify(plain_password, hashed_password)


def create_access_token(user_id: str, role: str, email: str) -> str:
  settings = get_settings()
  expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
  payload = {"sub": user_id, "role": role, "email": email, "exp": expire}
  return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


class TokenDecodeError(Exception):
  pass


def verify_access_token(token: str) -> dict:
  settings = get_settings()
  try:
    return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
  except JWTError as exc:
    raise TokenDecodeError("Invalid or expired token") from exc
