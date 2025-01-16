from sqlalchemy.dialects import registry  # noqa

from .main import *

__api__ = [
    "rename_schema",
    "get_frame_length",
    "rename_table",
    "vacuum_table",
    "drop_table",
    "rename_view",
    "drop_view",
    "rename_matview",
    "refresh_matview",
    "drop_matview",
    "rename_column",
    "drop_column",
    "conform",
]


registry.register(
    "mtsql_redshift",
    "mt.sql.redshift.dialect",
    "RedshiftDialect",
)
