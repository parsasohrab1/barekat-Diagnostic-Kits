"""Alembic migrations."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from barekat_diagnostics.core.config import get_settings
from barekat_diagnostics.core.database import Base
from barekat_diagnostics.models.audit import AuditLog  # noqa: F401
from barekat_diagnostics.models.fleet import (  # noqa: F401
  Center,
  EdgeDevice,
  FleetModelRelease,
  SyncConflictLog,
  Tenant,
)
from barekat_diagnostics.models.lis import FhirExport, LabOrder  # noqa: F401
from barekat_diagnostics.models.quality import (  # noqa: F401
  ChangeRequest,
  ClinicalValidationProtocol,
  DriftAlert,
  ModelBaseline,
)
from barekat_diagnostics.models.sample import (  # noqa: F401
  AssayBatch,
  BatchJob,
  Diagnosis,
  DiagnosisJob,
  KitCalibration,
  Sample,
)
from barekat_diagnostics.models.user import User  # noqa: F401

config = context.config
if config.config_file_name is not None:
  fileConfig(config.config_file_name)

settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
  url = config.get_main_option("sqlalchemy.url")
  context.configure(
    url=url,
    target_metadata=target_metadata,
    literal_binds=True,
    dialect_opts={"paramstyle": "named"},
  )
  with context.begin_transaction():
    context.run_migrations()


def run_migrations_online() -> None:
  connectable = engine_from_config(
    config.get_section(config.config_ini_section, {}),
    prefix="sqlalchemy.",
    poolclass=pool.NullPool,
  )
  with connectable.connect() as connection:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
      context.run_migrations()


if context.is_offline_mode():
  run_migrations_offline()
else:
  run_migrations_online()
