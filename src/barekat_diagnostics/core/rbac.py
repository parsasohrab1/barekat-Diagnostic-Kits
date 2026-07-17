"""Role-Based Access Control — operator / supervisor / admin.

Aliases برای سازگاری با نقش‌های قدیمی: technician→operator، pathologist→supervisor.
"""

from enum import Enum


class Role(str, Enum):
  OPERATOR = "operator"
  SUPERVISOR = "supervisor"
  ADMIN = "admin"


# نام‌های قدیمی که هنوز در توکن/DB ممکن است باشند
_ROLE_ALIASES: dict[str, Role] = {
  "technician": Role.OPERATOR,
  "pathologist": Role.SUPERVISOR,
  "operator": Role.OPERATOR,
  "supervisor": Role.SUPERVISOR,
  "admin": Role.ADMIN,
}


class Permission(str, Enum):
  SAMPLES_READ = "samples:read"
  SAMPLES_WRITE = "samples:write"
  DIAGNOSIS_RUN = "diagnosis:run"
  DIAGNOSIS_READ = "diagnosis:read"
  REPORTS_APPROVE = "reports:approve"
  CALIBRATION_MANAGE = "calibration:manage"
  ML_MANAGE = "ml:manage"
  ML_PROMOTE = "ml:promote"
  CHANGE_APPROVE = "change:approve"
  VALIDATION_SIGN = "validation:sign"
  AUDIT_READ = "audit:read"
  FHIR_EXPORT = "fhir:export"
  FHIR_IMPORT = "fhir:import"
  LIS_EXPORT = "lis:export"
  EDGE_OPERATE = "edge:operate"
  USERS_MANAGE = "users:manage"
  ADMIN_SETTINGS = "admin:settings"
  DRIFT_MANAGE = "drift:manage"


_OPERATOR_PERMS = {
  Permission.SAMPLES_READ,
  Permission.SAMPLES_WRITE,
  Permission.DIAGNOSIS_RUN,
  Permission.DIAGNOSIS_READ,
  Permission.CALIBRATION_MANAGE,
  Permission.FHIR_IMPORT,
  Permission.EDGE_OPERATE,
}

_SUPERVISOR_PERMS = {
  Permission.SAMPLES_READ,
  Permission.DIAGNOSIS_READ,
  Permission.REPORTS_APPROVE,
  Permission.FHIR_EXPORT,
  Permission.LIS_EXPORT,
  Permission.AUDIT_READ,
  Permission.ML_MANAGE,
  Permission.ML_PROMOTE,
  Permission.CHANGE_APPROVE,
  Permission.VALIDATION_SIGN,
  Permission.DRIFT_MANAGE,
}

_ADMIN_PERMS = set(Permission)

ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
  Role.OPERATOR: _OPERATOR_PERMS,
  Role.SUPERVISOR: _SUPERVISOR_PERMS,
  Role.ADMIN: _ADMIN_PERMS,
}


def normalize_role(role: str) -> Role | None:
  return _ROLE_ALIASES.get(role.lower().strip())


def has_permission(role: str, permission: Permission) -> bool:
  role_enum = normalize_role(role)
  if role_enum is None:
    return False
  return permission in ROLE_PERMISSIONS.get(role_enum, set())


def is_valid_role(role: str) -> bool:
  return normalize_role(role) is not None


def canonical_role(role: str) -> str:
  """برگرداندن نام canonical برای ذخیره در DB."""
  resolved = normalize_role(role)
  if resolved is None:
    raise ValueError(f"نقش نامعتبر: {role}")
  return resolved.value
