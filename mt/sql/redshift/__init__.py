from pkg_resources import DistributionNotFound, get_distribution, parse_version
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


for package in ["psycopg2", "psycopg2-binary", "psycopg2cffi"]:
    try:
        if get_distribution(package).parsed_version < parse_version("2.5"):
            raise ImportError("Minimum required version for psycopg2 is 2.5")
        break
    except DistributionNotFound:
        pass

registry.register("rs", "mt.sql.redshift.dialect", "RedshiftDialect_psycopg2")
registry.register("rs.psycopg2", "mt.sql.redshift.dialect", "RedshiftDialect_psycopg2")
registry.register(
    "rs+psycopg2cffi",
    "mt.sql.redshift.dialect",
    "RedshiftDialect_psycopg2cffi",
)

registry.register(
    "rs+redshift_connector",
    "mt.sql.redshift.dialect",
    "RedshiftDialect_redshift_connector",
)
