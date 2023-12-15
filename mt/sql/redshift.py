"""Useful modules for accessing Redshift"""

from mt import tp, logg

from .base import *


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
]


# ----- simple functions -----


def rename_schema(
    old_schema,
    new_schema,
    engine,
    nb_trials: int = 3,
    logger: tp.Optional[logg.IndentedLoggerAdapter] = None,
):
    """Renames a schema.

    Parameters
    ----------
    old_schema: str
        old schema name
    new_schema: str
        new schema name
    engine: sqlalchemy.engine.Engine
        an sqlalchemy connection engine created by function `create_engine()`
    nb_trials: int
        number of query trials
    logger: mt.logg.IndentedLoggerAdapter, optional
        logger for debugging
    """
    exec_sql(
        'ALTER SCHEMA "{}" RENAME TO "{}";'.format(old_schema, new_schema),
        engine,
        nb_trials=nb_trials,
        logger=logger,
    )


def get_frame_length(
    frame_name,
    engine,
    schema: tp.Optional[str] = None,
    nb_trials: int = 3,
    logger: tp.Optional[logg.IndentedLoggerAdapter] = None,
):
    """Gets the number of rows of a dataframes (tables/views/materialized views).

    Parameters
    ----------
    frame_name: str
        name of the dataframe
    engine: sqlalchemy.engine.Engine
        an sqlalchemy connection engine created by function `create_engine()`
    nb_trials: int
        number of query trials
    logger: mt.logg.IndentedLoggerAdapter, optional
        logger for debugging

    Returns
    -------
    out: int
        number of rows

    Notes
    -----
    The dataframe must exist.
    """
    frame_sql_str = frame_sql(frame_name, schema=schema)
    return read_sql(
        "SELECT COUNT(*) a FROM {};".format(frame_sql_str),
        engine,
        nb_trials=nb_trials,
        logger=logger,
    )["a"][0]


def rename_table(
    old_table_name,
    new_table_name,
    engine,
    schema: tp.Optional[str] = None,
    nb_trials: int = 3,
    logger: tp.Optional[logg.IndentedLoggerAdapter] = None,
):
    """Renames a table of a schema.

    Parameters
    ----------
    old_table_name: str
        old table name
    new_table_name: str
        new table name
    engine: sqlalchemy.engine.Engine
        an sqlalchemy connection engine created by function `create_engine()`
    schema: str or None
        a valid schema name returned from `list_schemas()`
    nb_trials: int
        number of query trials
    logger: mt.logg.IndentedLoggerAdapter, optional
        logger for debugging

    Returns
    -------
    whatever exec_sql() returns
    """
    frame_sql_str = frame_sql(old_table_name, schema=schema)
    return exec_sql(
        'ALTER TABLE {} RENAME TO "{}";'.format(frame_sql_str, new_table_name),
        engine,
        nb_trials=nb_trials,
        logger=logger,
    )


def drop_table(
    table_name,
    engine,
    schema: tp.Optional[str] = None,
    restrict=True,
    nb_trials: int = 3,
    logger: tp.Optional[logg.IndentedLoggerAdapter] = None,
):
    """Drops a table if it exists, with restrict or cascade options.

    Parameters
    ----------
    table_name : str
        table name
    engine: sqlalchemy.engine.Engine
        an sqlalchemy connection engine created by function `create_engine()`
    schema: str or None
        a valid schema name returned from `list_schemas()`
    restrict: bool
        If True, refuses to drop table if there is any object depending on it. Otherwise it is the
        'cascade' option which allows you to remove those dependent objects together with the table
        automatically.
    nb_trials: int
        number of query trials
    logger: mt.logg.IndentedLoggerAdapter, optional
        logger for debugging

    Returns
    -------
    whatever exec_sql() returns
    """
    frame_sql_str = frame_sql(table_name, schema=schema)
    query_str = "DROP TABLE IF EXISTS {} {};".format(
        frame_sql_str, "RESTRICT" if restrict else "CASCADE"
    )
    return exec_sql(query_str, engine, nb_trials=nb_trials, logger=logger)


def rename_view(
    old_view_name,
    new_view_name,
    engine,
    schema: tp.Optional[str] = None,
    nb_trials: int = 3,
    logger: tp.Optional[logg.IndentedLoggerAdapter] = None,
):
    """Renames a view of a schema.

    Parameters
    ----------
    old_view_name: str
        old view name
    new_view_name: str
        new view name
    engine: sqlalchemy.engine.Engine
        an sqlalchemy connection engine created by function `create_engine()`
    schema: str or None
        a valid schema name returned from `list_schemas()`
    nb_trials: int
        number of query trials
    logger: mt.logg.IndentedLoggerAdapter, optional
        logger for debugging
    """
    frame_sql_str = frame_sql(old_view_name, schema=schema)
    exec_sql(
        'ALTER VIEW {} RENAME TO "{}";'.format(frame_sql_str, new_view_name),
        engine,
        nb_trials=nb_trials,
        logger=logger,
    )


def drop_view(
    view_name,
    engine,
    schema: tp.Optional[str] = None,
    restrict=True,
    nb_trials: int = 3,
    logger: tp.Optional[logg.IndentedLoggerAdapter] = None,
):
    """Drops a view if it exists, with restrict or cascade options.

    Parameters
    ----------
    view_name: str
        view name
    engine: sqlalchemy.engine.Engine
        an sqlalchemy connection engine created by function `create_engine()`
    schema: str or None
        a valid schema name returned from `list_schemas()`
    restrict: bool
        If True, refuses to drop table if there is any object depending on it. Otherwise it is the
        'cascade' option which allows you to remove those dependent objects together with the table
        automatically.
    nb_trials: int
        number of query trials
    logger: mt.logg.IndentedLoggerAdapter, optional
        logger for debugging

    Returns
    -------
    whatever exec_sql() returns
    """
    frame_sql_str = frame_sql(view_name, schema=schema)
    query_str = "DROP VIEW IF EXISTS {} {};".format(
        frame_sql_str, "RESTRICT" if restrict else "CASCADE"
    )
    return exec_sql(query_str, engine, nb_trials=nb_trials, logger=logger)


def rename_matview(
    old_matview_name,
    new_matview_name,
    engine,
    schema: tp.Optional[str] = None,
    nb_trials: int = 3,
    logger: tp.Optional[logg.IndentedLoggerAdapter] = None,
):
    """Renames a materialized view of a schema.

    Parameters
    ----------
    old_matview_name: str
        old materialized view name
    new_matview_name: str
        new materialized view name
    engine: sqlalchemy.engine.Engine
        an sqlalchemy connection engine created by function `create_engine()`
    schema: str or None
        a valid schema name returned from `list_schemas()`
    nb_trials: int
        number of query trials
    logger: mt.logg.IndentedLoggerAdapter, optional
        logger for debugging
    """
    frame_sql_str = frame_sql(old_matview_name, schema=schema)
    exec_sql(
        'ALTER MATERIALIZED VIEW {} RENAME TO "{}";'.format(
            frame_sql_str, new_matview_name
        ),
        engine,
        nb_trials=nb_trials,
        logger=logger,
    )


def refresh_matview(
    matview_name,
    engine,
    schema: tp.Optional[str] = None,
    nb_trials: int = 3,
    logger: tp.Optional[logg.IndentedLoggerAdapter] = None,
):
    """Refreshes a materialized view of a schema.

    Parameters
    ----------
    matview_name: str
        materialized view name
    engine: sqlalchemy.engine.Engine
        an sqlalchemy connection engine created by function `create_engine()`
    schema: str or None
        a valid schema name returned from `list_schemas()`
    nb_trials: int
        number of query trials
    logger: mt.logg.IndentedLoggerAdapter, optional
        logger for debugging
    """
    frame_sql_str = frame_sql(matview_name, schema=schema)
    exec_sql(
        f"REFRESH MATERIALIZED VIEW {frame_sql_str};",
        engine,
        nb_trials=nb_trials,
        logger=logger,
    )


def drop_matview(
    matview_name,
    engine,
    schema: tp.Optional[str] = None,
    restrict=True,
    nb_trials: int = 3,
    logger: tp.Optional[logg.IndentedLoggerAdapter] = None,
):
    """Drops a mateiralized view if it exists, with restrict or cascade options.

    Parameters
    ----------
    matview_name: str
        materialized view name
    engine: sqlalchemy.engine.Engine
        an sqlalchemy connection engine created by function `create_engine()`
    schema: str or None
        a valid schema name returned from `list_schemas()`
    restrict: bool
        If True, refuses to drop table if there is any object depending on it. Otherwise it is the
        'cascade' option which allows you to remove those dependent objects together with the table
        automatically.
    nb_trials: int
        number of query trials
    logger: mt.logg.IndentedLoggerAdapter, optional
        logger for debugging

    Returns
    -------
    whatever exec_sql() returns
    """
    frame_sql_str = frame_sql(matview_name, schema=schema)
    query_str = "DROP MATERIALIZED VIEW IF EXISTS {} {};".format(
        frame_sql_str, "RESTRICT" if restrict else "CASCADE"
    )
    return exec_sql(query_str, engine, nb_trials=nb_trials, logger=logger)


def rename_column(
    table_name,
    old_column_name,
    new_column_name,
    engine,
    schema: tp.Optional[str] = None,
    nb_trials: int = 3,
    logger: tp.Optional[logg.IndentedLoggerAdapter] = None,
):
    """Renames a column of a table.

    Parameters
    ----------
    table_name: str
        table name
    old_column_name: str
        old column name
    new_column_name: str
        new column name
    engine: sqlalchemy.engine.Engine
        an sqlalchemy connection engine created by function `create_engine()`
    schema: str or None
        schema name
    nb_trials: int
        number of query trials
    logger: mt.logg.IndentedLoggerAdapter, optional
        logger for debugging
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
    exec_sql(query_str, engine, nb_trials=nb_trials, logger=logger)


def drop_column(
    table_name,
    column_name,
    engine,
    schema: tp.Optional[str] = None,
    nb_trials: int = 3,
    logger: tp.Optional[logg.IndentedLoggerAdapter] = None,
):
    """Drops a column of a table.

    Parameters
    ----------
    table_name: str
        table name
    column_name: str
        column name
    engine: sqlalchemy.engine.Engine
        an sqlalchemy connection engine created by function `create_engine()`
    schema: str or None
        schema name
    nb_trials: int
        number of query trials
    logger: mt.logg.IndentedLoggerAdapter, optional
        logger for debugging
    """
    column_name = column_name.replace("%", "%%")
    if schema is None:
        query_str = 'ALTER TABLE "{}" DROP COLUMN "{}";'.format(table_name, column_name)
    else:
        query_str = 'ALTER TABLE "{}"."{}" DROP COLUMN "{}";'.format(
            schema, table_name, column_name
        )
    exec_sql(query_str, engine, nb_trials=nb_trials, logger=logger)
