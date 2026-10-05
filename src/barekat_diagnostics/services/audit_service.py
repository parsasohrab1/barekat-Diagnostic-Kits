"""Authentication service."""

from sqlalchemy.orm import Session

from barekat_diagnostics.core.rbac import canonical_role, is_valid_role
from barekat_diagnostics.core.security import create_access_token, hash_password, verify_password
from barekat_diagnostics.models.user import User


class AuthService:
  def __init__(self, db: Session) -> None:
    self.db = db

  def authenticate(self, email: str, password: str) -> User | None:
    user = self.db.query(User).filter(User.email == email, User.is_active.is_(True)).first()
    if not user or not verify_password(password, user.hashed_password):
      return None
    return user

  def login(self, email: str, password: str) -> dict | None:
    user = self.authenticate(email, password)
    if not user:
      return None
    token = create_access_token(str(user.id), user.role, user.email)
    return {
      "access_token": token,
      "token_type": "bearer",
      "role": user.role,
      "email": user.email,
      "full_name": user.full_name,
    }

  def create_user(
    self,
    email: str,
    password: str,
    full_name: str,
    role: str = "operator",
  ) -> User:
    if not is_valid_role(role):
      raise ValueError(f"Invalid role: {role}")
    user = User(
      email=email,
      hashed_password=hash_password(password),
      full_name=full_name,
      role=canonical_role(role),
    )
    self.db.add(user)
    self.db.commit()
    self.db.refresh(user)
    return user
