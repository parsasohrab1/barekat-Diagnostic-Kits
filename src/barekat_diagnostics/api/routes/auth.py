"""API احراز هویت."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from barekat_diagnostics.api.deps import CurrentUser, get_current_user, require_permission
from barekat_diagnostics.core.database import get_db
from barekat_diagnostics.core.rbac import Permission
from barekat_diagnostics.schemas import AuthLoginResponse, UserCreateRequest
from barekat_diagnostics.services.audit_service import AuthService
from barekat_diagnostics.services.audit_trail import AuditTrailService

router = APIRouter(prefix="/auth")


@router.post("/login", response_model=AuthLoginResponse)
def login(
  form: OAuth2PasswordRequestForm = Depends(),
  db: Session = Depends(get_db),
) -> AuthLoginResponse:
  result = AuthService(db).login(form.username, form.password)
  if not result:
    raise HTTPException(status_code=401, detail="ایمیل یا رمز عبور نادرست است")
  AuditTrailService(db).log(
    "auth.login",
    actor_email=result["email"],
    actor_role=result["role"],
    resource_type="user",
    resource_id=result["email"],
  )
  return AuthLoginResponse(**result)


@router.post("/users", response_model=dict, status_code=201)
def create_user(
  body: UserCreateRequest,
  db: Session = Depends(get_db),
  user: CurrentUser = Depends(require_permission(Permission.USERS_MANAGE)),
) -> dict:
  try:
    created = AuthService(db).create_user(
      email=body.email,
      password=body.password,
      full_name=body.full_name,
      role=body.role,
    )
  except ValueError as exc:
    raise HTTPException(status_code=400, detail=str(exc)) from exc

  AuditTrailService(db).log(
    "user.created",
    actor_id=str(user.id),
    actor_email=user.email,
    actor_role=user.role,
    resource_type="user",
    resource_id=str(created.id),
    detail={"email": created.email, "role": created.role},
  )
  return {
    "id": str(created.id),
    "email": created.email,
    "full_name": created.full_name,
    "role": created.role,
  }


@router.get("/me")
def me(user: CurrentUser = Depends(get_current_user)) -> dict:
  return {
    "id": str(user.id),
    "email": user.email,
    "full_name": user.full_name,
    "role": user.role,
  }
