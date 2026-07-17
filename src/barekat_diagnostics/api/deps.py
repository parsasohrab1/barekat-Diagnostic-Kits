"""وابستگی‌های FastAPI: احراز هویت و RBAC."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from barekat_diagnostics.core.config import get_settings
from barekat_diagnostics.core.database import get_db
from barekat_diagnostics.core.rbac import Permission, has_permission
from barekat_diagnostics.core.security import TokenDecodeError, verify_access_token
from barekat_diagnostics.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


@dataclass
class CurrentUser:
  id: uuid.UUID
  email: str
  role: str
  full_name: str


_DEV_USER = CurrentUser(
  id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
  email="dev@barekat.local",
  role="admin",
  full_name="Dev Admin",
)


async def get_current_user(
  token: Annotated[str | None, Depends(oauth2_scheme)],
  db: Session = Depends(get_db),
) -> CurrentUser:
  settings = get_settings()
  if not settings.auth_enabled:
    return _DEV_USER

  if not token:
    raise HTTPException(
      status_code=status.HTTP_401_UNAUTHORIZED,
      detail="احراز هویت لازم است",
      headers={"WWW-Authenticate": "Bearer"},
    )

  try:
    payload = verify_access_token(token)
    user_id = uuid.UUID(payload["sub"])
  except (TokenDecodeError, KeyError, ValueError):
    raise HTTPException(
      status_code=status.HTTP_401_UNAUTHORIZED,
      detail="توکن نامعتبر",
      headers={"WWW-Authenticate": "Bearer"},
    )

  user = db.query(User).filter(User.id == str(user_id), User.is_active.is_(True)).first()
  if not user:
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="کاربر یافت نشد")

  return CurrentUser(
    id=uuid.UUID(str(user.id)),
    email=user.email,
    role=user.role,
    full_name=user.full_name,
  )


def require_permission(permission: Permission):
  async def checker(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if not has_permission(user.role, permission):
      raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"دسترسی مجاز نیست: {permission.value}",
      )
    return user

  return checker
