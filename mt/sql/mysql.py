"""Useful modules for accessing MySQL"""

import sqlalchemy as sa
import pandas as _pd
import re as _re
import mt.base.path as _p
from mt.base.bg_invoke import BgInvoke
import mt.pandas.csv as _mc

from .base import *


__all__ = [
    "list_views",
    "rename_table",
    "list_columns_ext",
    "list_columns",
    "rename_column",
    "drop_column",
]


# MT-TODO: any function below this line needs testing


def list_views(db_name, engine):
    """Lists all views of a given database.

    Parameters
    ----------
    db_name : str
        a valid dtabase name returned from `show_databases()`
    engine : sqlalchemy.engine.Engine
        an sqlalchemy connection engine created by function `create_engine()`

    Returns
    -------
    out : list
        list of all view names
    """
    text_sql = sa.text(
        "SHOW FULL TABLES IN '{}' WHERE TABLE_TYPE LIKE 'VIEW';".format(db_name)
    )
    df = _pd.read_sql_query(text_sql, engine)
    return df["viewname"].tolist()


def rename_table(old_table_name, new_table_name, engine, schema=None):
    """Renames a table of a schema.

    Parameters
    ----------
    old_table_name : str
        old table name
    new_table_name : str
        new table name
    engine : sqlalchemy.engine.Engine
        an sqlalchemy connection engine created by function `create_engine()`
    schema : str or None
        schema name
    """
    if schema is None:
        query_str = 'ALTER TABLE "{}" RENAME TO "{}";'.format(
            old_table_name, new_table_name
        )
    else:
        query_str = 'ALTER TABLE "{}"."{}" RENAME TO "{}";'.format(
            schema, old_table_name, new_table_name
        )
    engine_execute(engine, query_str)


def list_columns_ext(table_name, engine, schema=None):
    """Lists all columns of a given table of a given schema.

    Parameters
    ----------
    schema : str
        a valid schema name returned from `list_schemas()`
    table_name : str
        a valid table name returned from `list_tables()`
    engine : sqlalchemy.engine.Engine
        an sqlalchemy connection engine created by function `create_engine()`
    schema : str or None
        schema name

    Returns
    -------
    out : pandas.DataFrame
        a table of details of the columns
    """
    if schema is None:
        query_str = (
            "select * from information_schema.columns where table_name='{}';".format(
                table_name
            )
        )
    else:
        query_str = "select * from information_schema.columns where table_schema='{}' and table_name='{}';".format(
            schema, table_name
        )
    text_sql = sa.text(query_str) if isinstance(query_str, str) else query_str
    return _pd.read_sql_query(text_sql, engine)


def list_columns(table_name, engine, schema=None):
    """Lists all columns of a given table of a given schema.

    Parameters
    ----------
    table_name : str
        a valid table name returned from `list_tables()`
    engine : sqlalchemy.engine.Engine
        an sqlalchemy connection engine created by function `create_engine()`
    schema : str or None
        schema name

    Returns
    -------
    out : list of all column names
    """
    return list_columns_ext(table_name, engine, schema=schema)["column_name"].tolist()


def rename_column(table_name, old_column_name, new_column_name, engine, schema=None):
    """Renames a column of a table.

    Parameters
    ----------
    table_name : str
        table name
    old_column_name : str
        old column name
    new_column_name : str
        new column name
    engine : sqlalchemy.engine.Engine
        an sqlalchemy connection engine created by function `create_engine()`
    schema : str or None
        schema name
    """
    old_column_name = old_column_name.replace("%", "%%")
    if schema is None:
        query_str = 'ALTER TABLE "{}" RENAME COLUMN "{}" TO "{}";'.format(
            table_name, old_column_name, new_column_name
        )
    else:
        query_str = 'ALTER TABLE "{}"."{}" RENAME COLUMN "{}" TO "{}";'.format(
            schema, table_name, old_column_name, new_column_name
        )
    engine_execute(engine, query_str)


def drop_column(table_name, column_name, engine, schema=None):
    """Drops a column of a table.

    Parameters
    ----------
    table_name : str
        table name
    column_name : str
        column name
    engine : sqlalchemy.engine.Engine
        an sqlalchemy connection engine created by function `create_engine()`
    schema : str or None
        schema name
    """
    column_name = column_name.replace("%", "%%")
    if schema is None:
        query_str = 'ALTER TABLE "{}" DROP COLUMN "{}";'.format(table_name, column_name)
    else:
        query_str = 'ALTER TABLE "{}"."{}" DROP COLUMN "{}";'.format(
            schema, table_name, column_name
        )
    engine_execute(engine, query_str)
