"""Useful modules for accessing PostgreSQL"""

from typing import Optional

import re
import psycopg2 as ps
import sqlalchemy.exc as se
from tqdm import tqdm  # nice progress bar

from mt import pd, np
import mt.base.path as _p
from mt.base.bg_invoke import BgInvoke
from mt.base.with_utils import dummy_scope

from .base import *


__all__ = [
    "pg_get_locked_transactions",
    "pg_cancel_backend",
    "pg_cancel_all_backends",
    "indices",
    "compliance_check",
    "as_column_name",
    "to_sql",
    "rename_schema",
    "list_views",
    "list_matviews",
    "list_frames",
    "list_all_frames",
    "get_frame_length",
    "get_frame_dependencies",
    "get_view_sql_code",
    "rename_table",
    "drop_table",
    "rename_view",
    "drop_view",
    "rename_matview",
    "drop_matview",
    "frame_exists",
    "drop_frame",
    "list_columns_ext",
    "list_columns",
    "list_primary_columns_ext",
    "list_primary_columns",
    "rename_column",
    "drop_column",
    "comparesync_table",
    "readsync_table",
    "writesync_table",
]


# ----- debugging functions -----


def pg_get_locked_transactions(engine, schema: Optional[str] = None):
    """Obtains a dataframe representing transactions which have been locked by the server.

    Parameters
    ----------
    engine: sqlalchemy.engine.Engine
        connection engine
    schema: str or None
        If None, then all schemas are considered and not just the public schema. Else, scope down to a single schema.

    Returns
    -------
    pd.DataFrame
        A table containing the current backend transactions
    """
    if schema is None:
        query_str = """
            SELECT
                t1.*, t2.relname, t3.nspname
              FROM pg_locks t1
                INNER JOIN pg_class t2 ON t1.relation=t2.oid
                INNER JOIN pg_namespace t3 ON t2.relnamespace=t3.oid
              WHERE NOT t2.relname ILIKE 'pg_%%'
            ;"""
    else:
        query_str = """
            SELECT
                t1.*, t2.relname, t3.nspname
              FROM pg_locks t1
                INNER JOIN pg_class t2 ON t1.relation=t2.oid
                INNER JOIN pg_namespace t3 ON t2.relnamespace=t3.oid
              WHERE NOT t2.relname ILIKE 'pg_%%'
                AND t3.nspname = '{}'
            ;""".format(
            schema
        )
    return pd.read_sql(query_str, engine)


def pg_cancel_backend(engine, pid):
    """Cancels a backend transaction given its pid.

    Parameters
    ----------
    engine: sqlalchemy.engine.Engine
        connection engine
    pid: int
        the backend pid to be cancelled
    """
    query_str = "SELECT pg_cancel_backend('{}');".format(pid)
    return pd.read_sql(query_str, engine)


def pg_cancel_all_backends(engine, schema: Optional[str] = None, logger=None):
    """Cancels all backend transactions.

    Parameters
    ----------
    engine: sqlalchemy.engine.Engine
        connection engine
    schema: str or None
        If None, then all schemas are considered and not just the public schema. Else, scope down to a single schema.
    logger: logging.Logger or None
        logger for debugging
    """
    df = pg_get_locked_transactions(engine, schema=schema)
    pids = df["pid"].drop_duplicates().tolist()
    for pid in pids:
        if logger:
            logger.info("Cancelling backend pid {}".format(pid))
        pg_cancel_backend(engine, pid)


# ----- functions dealing with sql queries to overcome OperationalError -----


def indices(df):
    """Returns the list of named indices of the dataframe, ignoring any unnamed index."""
    a = list(df.index.names)
    return a if a != [None] else []


def compliance_check(df):
    """Checks if a dataframe is compliant to PSQL. It must have no index, or indices which do not match with any column. Raises ValueError when an error is encountered."""
    for x in indices(df):
        if x in df.columns:
            raise ValueError(
                "Index '{}' appears as a non-primary column as well".format(x)
            )


def as_column_name(s):
    """Converts a string into a PSQL-compliant column name.

    Parameters
    ----------
    s: str
        a string

    Returns
    -------
    s2: str
        a lower-case alpha-numeric and underscore-only string

    Raises
    ------
    ValueError if the string cannot be converted.
    """
    if not isinstance(s, str):
        raise ValueError("The input argument is not a string: {}".format(s))

    s2 = re.sub("[^\w]", "_", s)
    s2 = s2.lower()
    if not re.match("^[a-z]", s2):
        raise ValueError(
            "The first letter of the input is not an alphabet letter: '{}'->'{}'".format(
                s, s2
            )
        )

    return s2


def to_sql(
    df,
    name,
    engine,
    schema: Optional[str] = None,
    if_exists="fail",
    nb_trials: int = 3,
    logger=None,
    **kwargs
):
    """Writes records stored in a DataFrame to an SQL database, with a number of trials to overcome OperationalError.

    Parameters
    ----------
    df : pandas.DataFrame
        dataframe to be sent to the server
    name : str
        name of the table to be written to
    engine : sqlalchemy.engine.Engine
        connection engine to the server
    schema: string, optional
        Specify the schema. If None, use default schema.
    if_exists: str
        what to do when the table exists. Beside all options available from pandas.to_sql(), a new option called 'gently_replace' is introduced, in which it will avoid dropping the table by trying to delete all entries and then inserting new entries. But it will only do so if the remote table contains exactly all the columns that the local dataframe has, and vice-versa.
    nb_trials: int
        number of query trials
    logger: logging.Logger or None
        logger for debugging

    Raises
    ------
    sqlalchemy.exc.ProgrammingError if the local and remote frames do not have the same structure

    Notes
    -----
    The original pandas.DataFrame.to_sql() function does not turn any index into a primary key in PSQL. This function attempts to fix that problem. It takes as input a PSQL-compliant dataframe (see `compliance_check()`). It ignores any input `index` or `index_label` keyword. Instead, it considers 2 cases. If the dataframe's has an index or indices, then the tuple of all indices is turned into the primary key. If not, there is no primary key and no index is uploaded.

    See Also
    --------
    pandas.DataFrame.to_sql()

    """

    if kwargs:
        if "index" in kwargs:
            raise ValueError(
                "The `mt.sql.psql.to_sql()` function does not accept `index` as a keyword."
            )
        if "index_label" in kwargs:
            raise ValueError(
                "This `mt.sql.psql.to_sql()` function does not accept `index_label` as a keyword."
            )

    compliance_check(df)
    frame_sql_str = frame_sql(name, schema=schema)

    # if the remote frame does not exist, force `if_exists` to 'replace'
    if not frame_exists(
        name, engine, schema=schema, nb_trials=nb_trials, logger=logger
    ):
        if_exists = "replace"
    local_indices = indices(df)

    # not 'gently replace' case
    if if_exists != "gently_replace":
        if not local_indices:
            return run_func(
                df.to_sql,
                name,
                engine,
                schema=schema,
                if_exists=if_exists,
                index=False,
                index_label=None,
                nb_trials=nb_trials,
                logger=logger,
                **kwargs
            )
        retval = run_func(
            df.to_sql,
            name,
            engine,
            schema=schema,
            if_exists=if_exists,
            index=True,
            index_label=None,
            nb_trials=nb_trials,
            logger=logger,
            **kwargs
        )
        if if_exists == "replace":
            exec_sql(
                "ALTER TABLE {} ADD PRIMARY KEY ({});".format(
                    frame_sql_str, ",".join(local_indices)
                ),
                engine,
                nb_trials=nb_trials,
                logger=logger,
            )
        return retval

    # the remaining section is the 'gently replace' case

    # remote indices
    remote_indices = list_primary_columns(
        name, engine, schema=schema, nb_trials=nb_trials, logger=logger
    )
    if local_indices != remote_indices:
        raise se.ProgrammingError(
            "SELECT * FROM {} LIMIT 1;".format(frame_sql_str),
            remote_indices,
            "Remote index '{}' differs from local index '{}'.".format(
                remote_indices, local_indices
            ),
        )

    # remote columns
    remote_columns = list_columns(
        name, engine, schema=schema, nb_trials=nb_trials, logger=logger
    )
    remote_columns = [x for x in remote_columns if not x in remote_indices]
    columns = list(df.columns)
    if columns != remote_columns:
        raise se.ProgrammingError(
            "SELECT * FROM {} LIMIT 1;".format(frame_sql_str),
            "matching non-primary fields",
            "Local columns '{}' differ from remote columns '{}'.".format(
                columns, remote_columns
            ),
        )

    exec_sql(
        "DELETE FROM {};".format(frame_sql_str),
        engine,
        nb_trials=nb_trials,
        logger=logger,
    )
    return run_func(
        df.to_sql,
        name,
        engine,
        schema=schema,
        if_exists="append",
        index=bool(local_indices),
        index_label=None,
        nb_trials=nb_trials,
        logger=logger,
        **kwargs
    )


# ----- simple functions -----


def rename_schema(old_schema, new_schema, engine, nb_trials: int = 3, logger=None):
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
    logger: logging.Logger or None
        logger for debugging
    """
    exec_sql(
        'ALTER SCHEMA "{}" RENAME TO "{}";'.format(old_schema, new_schema),
        engine,
        nb_trials=nb_trials,
        logger=logger,
    )


def list_views(engine, schema: Optional[str] = None, nb_trials: int = 3, logger=None):
    """Lists all views of a given schema.

    Parameters
    ----------
    engine: sqlalchemy.engine.Engine
        an sqlalchemy connection engine created by function `create_engine()`
    schema: str or None
        a valid schema name returned from `list_schemas()`
    nb_trials: int
        number of query trials
    logger: logging.Logger or None
        logger for debugging

    Returns
    -------
    out: list
        list of all view names
    """
    if schema is None:
        query_str = "select distinct viewname from pg_views;"
    else:
        query_str = (
            "select distinct viewname from pg_views where schemaname='{}';".format(
                schema
            )
        )
    df = read_sql_query(query_str, engine, nb_trials=nb_trials, logger=logger)
    return df["viewname"].tolist()


def list_matviews(
    engine, schema: Optional[str] = None, nb_trials: int = 3, logger=None
):
    """Lists all materialized views of a given schema.

    Parameters
    ----------
    engine: sqlalchemy.engine.Engine
        an sqlalchemy connection engine created by function `create_engine()`
    schema: str or None
        a valid schema name returned from `list_schemas()`
    nb_trials: int
        number of query trials
    logger: logging.Logger or None
        logger for debugging

    Returns
    -------
    out: list
        list of all materialized view names
    """
    if schema is None:
        schema = "public"
    query_str = (
        "select distinct matviewname from pg_matviews where schemaname='{}';".format(
            schema
        )
    )
    df = read_sql_query(query_str, engine, nb_trials=nb_trials, logger=logger)
    return df["matviewname"].tolist()


def list_frames(engine, schema: Optional[str] = None, nb_trials: int = 3, logger=None):
    """Lists all dataframes (tables/views/materialized views) of a given schema.

    Parameters
    ----------
    engine: sqlalchemy.engine.Engine
        an sqlalchemy connection engine created by function `create_engine()`
    schema: str or None
        a valid schema name returned from `list_schemas()`
    nb_trials: int
        number of query trials
    logger: logging.Logger or None
        logger for debugging

    Returns
    -------
    out: pd.DataFrame(columns=['name', 'type'])
        list of all dataframes of types {'table', 'view', 'matview'}
    """
    data = []
    for item in list_tables(engine, schema=schema, nb_trials=nb_trials, logger=logger):
        data.append((item, "table"))
    for item in list_views(engine, schema=schema, nb_trials=nb_trials, logger=logger):
        data.append((item, "view"))
    for item in list_matviews(
        engine, schema=schema, nb_trials=nb_trials, logger=logger
    ):
        data.append((item, "matview"))
    return pd.DataFrame(data=data, columns=["name", "type"])


def list_all_frames(
    engine, schema: Optional[str] = None, nb_trials: int = 3, logger=None
):
    """Lists all dataframes (tables/views/materialized views) across all schemas.

    Parameters
    ----------
    engine: sqlalchemy.engine.Engine
        an sqlalchemy connection engine created by function `create_engine()`
    nb_trials: int
        number of query trials
    logger: logging.Logger or None
        logger for debugging

    Returns
    -------
    out: pd.DataFrame(columns=['name', 'schema', 'type'])
        list of all dataframes of types {'table', 'view', 'matview'}
    """
    dfs = []
    for schema in list_schemas(engine, nb_trials=nb_trials, logger=logger):
        df = list_frames(engine, schema=schema, nb_trials=nb_trials, logger=logger)
        if len(df) > 0:
            df["schema"] = schema
            dfs.append(df)
    return pd.concat(dfs, sort=False).reset_index(drop=True)


def get_frame_length(
    frame_name, engine, schema: Optional[str] = None, nb_trials: int = 3, logger=None
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
    logger: logging.Logger or None
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
    return read_sql_query(
        "SELECT COUNT(*) a FROM {};".format(frame_sql_str),
        engine,
        nb_trials=nb_trials,
        logger=logger,
    )["a"][0]


def get_frame_dependencies(
    frame_name, engine, schema: Optional[str] = None, nb_trials: int = 3, logger=None
):
    """Gets the list of all frames that depend on the given frame."""
    query_str = """
        SELECT dependent_ns.nspname as dependent_schema
        , dependent_view.relname as dependent_view
        , source_ns.nspname as source_schema
        , source_table.relname as source_table
        , pg_attribute.attname as column_name
        FROM pg_depend
        JOIN pg_rewrite ON pg_depend.objid = pg_rewrite.oid
        JOIN pg_class as dependent_view ON pg_rewrite.ev_class = dependent_view.oid
        JOIN pg_class as source_table ON pg_depend.refobjid = source_table.oid
        JOIN pg_attribute ON pg_depend.refobjid = pg_attribute.attrelid
            AND pg_depend.refobjsubid = pg_attribute.attnum
        JOIN pg_namespace dependent_ns ON dependent_ns.oid = dependent_view.relnamespace
        JOIN pg_namespace source_ns ON source_ns.oid = source_table.relnamespace
        WHERE
        source_ns.nspname = '{}'
        AND source_table.relname = '{}'
        AND pg_attribute.attnum > 0
        ORDER BY 1,2;
    """.format(
        "public" if schema is None else schema, frame_name
    )
    return read_sql_query(query_str, engine, nb_trials=nb_trials, logger=logger)


def get_view_sql_code(
    view_name, engine, schema: Optional[str] = None, nb_trials: int = 3, logger=None
):
    """Gets the SQL string of a view.

    Parameters
    ----------
    view_name: str
        view name
    engine: sqlalchemy.engine.Engine
        an sqlalchemy connection engine created by function `create_engine()`
    schema: str or None
        a valid schema name returned from `list_schemas()`
    nb_trials: int
        number of query trials
    logger: logging.Logger or None
        logger for debugging

    Returns
    -------
    retval: str
        SQL query string defining the view
    """
    return read_sql_query(
        "SELECT pg_get_viewdef('{}', true) a".format(
            frame_sql(view_name, schema=schema)
        ),
        engine,
        nb_trials=nb_trials,
        logger=logger,
    )["a"][0]


def rename_table(
    old_table_name,
    new_table_name,
    engine,
    schema: Optional[str] = None,
    nb_trials: int = 3,
    logger=None,
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
    logger: logging.Logger or None
        logger for debugging

    Returns
    -------
    whatever exec_sql() returns
    """
    frame_sql_str = frame_sql(old_table_name, schema=schema)
    exec_sql(
        'ALTER TABLE {} RENAME TO "{}";'.format(frame_sql_str, new_table_name),
        engine,
        nb_trials=nb_trials,
        logger=logger,
    )


def drop_table(
    table_name,
    engine,
    schema: Optional[str] = None,
    restrict=True,
    nb_trials: int = 3,
    logger=None,
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
        If True, refuses to drop table if there is any object depending on it. Otherwise it is the 'cascade' option which allows you to remove those dependent objects together with the table automatically.
    nb_trials: int
        number of query trials
    logger: logging.Logger or None
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
    schema: Optional[str] = None,
    nb_trials: int = 3,
    logger=None,
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
    logger: logging.Logger or None
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
    schema: Optional[str] = None,
    restrict=True,
    nb_trials: int = 3,
    logger=None,
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
        If True, refuses to drop table if there is any object depending on it. Otherwise it is the 'cascade' option which allows you to remove those dependent objects together with the table automatically.
    nb_trials: int
        number of query trials
    logger: logging.Logger or None
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
    schema: Optional[str] = None,
    nb_trials: int = 3,
    logger=None,
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
    logger: logging.Logger or None
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


def drop_matview(
    matview_name,
    engine,
    schema: Optional[str] = None,
    restrict=True,
    nb_trials: int = 3,
    logger=None,
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
        If True, refuses to drop table if there is any object depending on it. Otherwise it is the 'cascade' option which allows you to remove those dependent objects together with the table automatically.
    nb_trials: int
        number of query trials
    logger: logging.Logger or None
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


def frame_exists(
    frame_name, engine, schema: Optional[str] = None, nb_trials: int = 3, logger=None
):
    """Checks if a frame exists.

    Parameters
    ----------
    frame_name: str
        name of table or view
    engine: sqlalchemy.engine.Engine
        an sqlalchemy connection engine created by function `create_engine()`
    schema: str or None
        a valid schema name returned from `list_schemas()`
    nb_trials: int
        number of query trials
    logger: logging.Logger or None
        logger for debugging

    Returns
    -------
    retval: bool
        whether a table or a view exists with the given name
    """
    if frame_name in list_tables(
        engine, schema=schema, nb_trials=nb_trials, logger=logger
    ):
        return True
    if frame_name in list_views(
        engine, schema=schema, nb_trials=nb_trials, logger=logger
    ):
        return True
    return frame_name in list_matviews(
        engine, schema=schema, nb_trials=nb_trials, logger=logger
    )


def drop_frame(
    frame_name,
    engine,
    schema: Optional[str] = None,
    restrict=True,
    nb_trials: int = 3,
    logger=None,
):
    """Drops a frame (table/view/mateiralized view) if it exists, with restrict or cascade options.

    Parameters
    ----------
    frame_name: str
        frame name
    engine: sqlalchemy.engine.Engine
        an sqlalchemy connection engine created by function `create_engine()`
    schema: str or None
        a valid schema name returned from `list_schemas()`
    restrict: bool
        If True, refuses to drop table if there is any object depending on it. Otherwise it is the 'cascade' option which allows you to remove those dependent objects together with the table automatically.
    nb_trials: int
        number of query trials
    logger: logging.Logger or None
        logger for debugging

    Returns
    -------
    whatever exec_sql() returns, or False if the frame does not exist
    """
    if frame_name in list_tables(
        engine, schema=schema, nb_trials=nb_trials, logger=logger
    ):
        return drop_table(
            frame_name,
            engine,
            schema=schema,
            restrict=restrict,
            nb_trials=nb_trials,
            logger=logger,
        )
    if frame_name in list_views(
        engine, schema=schema, nb_trials=nb_trials, logger=logger
    ):
        return drop_view(
            frame_name,
            engine,
            schema=schema,
            restrict=restrict,
            nb_trials=nb_trials,
            logger=logger,
        )
    if frame_name in list_matviews(
        engine, schema=schema, nb_trials=nb_trials, logger=logger
    ):
        return drop_matview(
            frame_name,
            engine,
            schema=schema,
            restrict=restrict,
            nb_trials=nb_trials,
            logger=logger,
        )
    return False


def list_columns_ext(
    table_name, engine, schema: Optional[str] = None, nb_trials: int = 3, logger=None
):
    """Lists all columns of a given table of a given schema.

    Parameters
    ----------
    table_name: str
        a valid table name returned from `list_tables()`
    engine: sqlalchemy.engine.Engine
        an sqlalchemy connection engine created by function `create_engine()`
    schema: str or None
        a valid schema name returned from `list_schemas()`
    nb_trials: int
        number of query trials
    logger: logging.Logger or None
        logger for debugging

    Returns
    -------
    out: pandas.DataFrame
        a table of details of the columns
    """
    if not frame_exists(
        table_name, engine, schema=schema, nb_trials=nb_trials, logger=logger
    ):
        if schema is None:
            s = "Table or view with name '{}' does not exists.".format(table_name)
        else:
            s = "Table or view with name '{}' from schema '{}' does not exists.".format(
                table_name, schema
            )
        raise ps.ProgrammingError(s)

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

    return read_sql_query(query_str, engine, nb_trials=nb_trials, logger=logger)


def list_columns(
    table_name, engine, schema: Optional[str] = None, nb_trials: int = 3, logger=None
):
    """Lists all columns of a given table of a given schema.

    Parameters
    ----------
    table_name: str
        a valid table name returned from `list_tables()`
    engine: sqlalchemy.engine.Engine
        an sqlalchemy connection engine created by function `create_engine()`
    schema: str or None
        a valid schema name returned from `list_schemas()`
    nb_trials: int
        number of query trials
    logger: logging.Logger or None
        logger for debugging

    Returns
    -------
    out: list of all column names
    """
    return list_columns_ext(
        table_name, engine, schema=schema, nb_trials=nb_trials, logger=logger
    )["column_name"].tolist()


def list_primary_columns_ext(
    frame_name, engine, schema: Optional[str] = None, nb_trials: int = 3, logger=None
):
    """Lists all primary columns of a given frame of a given schema.

    Parameters
    ----------
    frame_name: str
        a valid table/view/matview name returned from `list_frames()`
    engine: sqlalchemy.engine.Engine
        an sqlalchemy connection engine created by function `create_engine()`
    schema: str or None
        a valid schema name returned from `list_schemas()`
    nb_trials: int
        number of query trials
    logger: logging.Logger or None
        logger for debugging

    Returns
    -------
    pandas.DataFrame
        dataframe containing primary column names and data types
    """
    frame_sql_str = frame_sql(frame_name, schema=schema)
    query_str = """
        SELECT a.attname, format_type(a.atttypid, a.atttypmod) AS data_type
        FROM   pg_index i
        JOIN   pg_attribute a ON a.attrelid = i.indrelid
                             AND a.attnum = ANY(i.indkey)
        WHERE  i.indrelid = '{}'::regclass
        AND    i.indisprimary;
        """.format(
        frame_sql_str
    )
    return read_sql_query(query_str, engine, nb_trials=nb_trials, logger=logger)


def list_primary_columns(
    frame_name, engine, schema: Optional[str] = None, nb_trials: int = 3, logger=None
):
    """Lists all primary columns of a given frame of a given schema.

    Parameters
    ----------
    frame_name: str
        a valid table/view/matview name returned from `list_frames()`
    engine: sqlalchemy.engine.Engine
        an sqlalchemy connection engine created by function `create_engine()`
    schema: str or None
        a valid schema name returned from `list_schemas()`
    nb_trials: int
        number of query trials
    logger: logging.Logger or None
        logger for debugging

    Returns
    -------
    list
        list of primary column names
    """
    return list_primary_columns_ext(
        frame_name, engine, schema=schema, nb_trials=nb_trials, logger=logger
    )["attname"].tolist()


def rename_column(
    table_name,
    old_column_name,
    new_column_name,
    engine,
    schema: Optional[str] = None,
    nb_trials: int = 3,
    logger=None,
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
    logger: logging.Logger or None
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
    schema: Optional[str] = None,
    nb_trials: int = 3,
    logger=None,
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
    logger: logging.Logger or None
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


# ----- functions to synchronise between a local table and a remote table -----


def comparesync_table(
    engine,
    df_filepath,
    table_name,
    id_name,
    hash_name="hash",
    columns=["*"],
    schema: Optional[str] = None,
    max_records_per_query=None,
    cond=None,
    reading_mode=True,
    nb_trials: int = 3,
    logger=None,
):
    """Compares a local CSV table with a remote PostgreSQL to find out which rows are the same or different.

    Parameters
    ----------
    engine: sqlalchemy connectible
        connection to the PostgreSQL database
    df_filepath: path
        path to the local '.csv', '.csv.zip' or '.parquet' file
    table_name: str
        table name
    id_name: str
        index column name. Assumption is only one column for indexing for now.
    hash_name : str
        Name of the hash field that only changes when the row changes. If reading_mode is True and the field does not exist remotely, it will be generated by the remote server via md5. If reading_mode is False and the field does not exist locally, it will be generate locally using hashlib.
    columns: list
        list of column names the function will read from, ignoring the remaining columns
    schema: str
        schema name, None means using the default one
    max_records_per_query: int or None
        maximum number of records to be updated in each SQL query. If None, this will be dynamic to make sure each query runs about 5 minute.
    cond: str
        additional condition in selecting rows from the PostgreSQL table
    reading_mode: bool
        whether comparing is for reading or for writing
    nb_trials: int
        number of read_sql() trials
    logger: logging.Logger or None
        logger for debugging

    Returns
    -------
    local_df: `pandas.DataFrame(index=id_name, columns=[..., hash_name])` or None
        local dataframe loaded to memory, if it exists
    remote_md5_df: pandas.DataFrame(index=id_name, columns=[hash_name])
        remote dataframe containing only the hash values
    same_keys: list
        list of keys identifying rows which appear in both tables and are the same
    diff_keys: list
        list of keys identifying rows which appear in both tables but are different
    local_only_keys: list
        list of keys containing rows which appear in the local table only
    remote_only_keys: list
        list of keys identifying rows which appear in the remote table only

    Notes
    -----
    The hash field of each table will be used to store and compare the hash values. If it does not exist, it will be generated automatically.

    The id_name field must uniquely identify each record in both tables. Duplicated keys in either table will be treated as diff_keys, so that hopefully next sync will fix them.
    """
    frame_sql_str = frame_sql(table_name, schema=schema)

    with logger.scoped_debug(
        "Comparing table: local '{}' <-> remote '{}'".format(
            df_filepath, frame_sql_str
        ),
        curly=False,
    ) if logger else dummy_scope:
        # make sure the folder containing the CSV file exists
        data_dir = _p.dirname(df_filepath)
        _p.make_dirs(data_dir)

        # local_df
        if _p.exists(df_filepath):
            try:
                if df_filepath.endswith(".parquet"):
                    local_df = pd.dfload(df_filepath, show_progress=True)
                else:
                    local_df = pd.dfload(
                        df_filepath, index_col=id_name, show_progress=True
                    )
                local_dup_keys = (
                    local_df[local_df.index.duplicated()]
                    .index.drop_duplicates()
                    .tolist()
                )
                if len(local_df) == 0:
                    local_df = None
                elif hash_name not in local_df.columns:
                    local_df[hash_name] = pd.util.hash_pandas_object(
                        local_df, index=False, hash_key="emerus_pham_2015"
                    ).astype(np.int64)
            except ValueError as e:
                if logger:
                    logger.warn("Ignored exception: {}".format(str(e)))
                    logger.warn_last_exception()
                local_df = None
        else:
            local_df = None
            local_dup_keys = []

        # local_md5_df
        if local_df is not None:
            if logger:
                logger.debug("The local table has {} records.".format(len(local_df)))
            local_md5_df = local_df[[hash_name]]
        else:
            if logger:
                logger.debug("The local table is empty.")
            local_md5_df = pd.DataFrame(
                index=pd.Index([], name=id_name), columns=[hash_name]
            )

        # remote_md5_df
        try:
            column_list = ",".join((table_name + "." + x for x in columns))
            if columns == ["*"]:
                text = "textin(record_out(" + column_list + "))"
            else:
                text = "textin(record_out((" + column_list + ")))"

            if hash_name in list_columns(
                table_name, engine, schema=schema, nb_trials=nb_trials, logger=logger
            ):
                query_str = "select {}, {} from {}".format(
                    id_name, hash_name, frame_sql_str
                )
            else:
                query_str = "select {}, md5({}) as {} from {}".format(
                    id_name, text, hash_name, frame_sql_str
                )

            with logger.scoped_debug(
                "Range of '{}'".format(id_name), curly=False
            ) if logger else dummy_scope:
                qsql = "SELECT min({}) AS val FROM ({}) ct_t0".format(
                    id_name, query_str
                )
                df = read_sql(qsql, engine, nb_trials=nb_trials, logger=logger)
                min_id = df["val"][0]
                if logger:
                    logger.debug("Min: {}".format(min_id))
                qsql = "SELECT max({}) AS val FROM ({}) ct_t0".format(
                    id_name, query_str
                )
                df = read_sql(qsql, engine, nb_trials=nb_trials, logger=logger)
                max_id = df["val"][0]
                if logger:
                    logger.debug("Max: {}".format(max_id))

            remaining = max_id + 1 - min_id
            offset = max_id + 1
            remote_md5_dfs = []
            record_cap = 128
            if logger:
                logger.debug("Obtaining remote keys and hashes:")
            with tqdm(total=remaining, unit="val") as progress_bar:
                while remaining > record_cap:
                    if cond:
                        qsql = "{} where {} and {}>={} and {}<{}".format(
                            query_str,
                            cond,
                            id_name,
                            offset - record_cap,
                            id_name,
                            offset,
                        )
                    else:
                        qsql = "{} where {}>={} and {}<{}".format(
                            query_str, id_name, offset - record_cap, id_name, offset
                        )
                    # if logger:
                    # logger.debug("offset={} record_cap={}".format(
                    # offset, record_cap))

                    start_time = pd.Timestamp.utcnow()
                    df = read_sql(
                        qsql,
                        engine,
                        index_col=id_name,
                        nb_trials=nb_trials,
                        logger=logger,
                    )
                    remote_md5_dfs.append(df)
                    # elapsed time is in seconds
                    elapsed_time = (pd.Timestamp.utcnow() - start_time).total_seconds()

                    progress_bar.update(record_cap)
                    offset -= record_cap
                    remaining -= record_cap

                    if max_records_per_query is None:
                        if elapsed_time > 300:  # too slow
                            record_cap = max(1, record_cap // 2)
                        else:  # too fast
                            record_cap *= 2

                if cond:
                    qsql = "{} where {} and {}>={} and {}<{}".format(
                        query_str, cond, id_name, min_id, id_name, offset
                    )
                else:
                    qsql = "{} where {}>={} and {}<{}".format(
                        query_str, id_name, min_id, id_name, offset
                    )

                df = read_sql(
                    qsql,
                    engine,
                    index_col=id_name,
                    nb_trials=nb_trials,
                    logger=logger,
                )
                remote_md5_dfs.append(df)
                remote_md5_df = pd.concat(remote_md5_dfs, sort=False)

                progress_bar.update(remaining)

            remote_dup_keys = (
                remote_md5_df[remote_md5_df.index.duplicated()]
                .index.drop_duplicates()
                .tolist()
            )
            if logger:
                logger.debug(
                    "The remote table has {} records.".format(len(remote_md5_df))
                )
        # table does not exist or does not have the columns we wanted
        except (se.ProgrammingError, ps.ProgrammingError):
            if reading_mode:
                raise
            if logger:
                logger.warn("Ignoring the following exception.")
                logger.warn_last_exception()
            remote_md5_df = pd.DataFrame(
                index=pd.Index([], name=id_name), columns=[hash_name]
            )
            remote_dup_keys = []
            if logger:
                logger.debug("The remote table is empty.")

        # compare
        df = local_md5_df.join(
            remote_md5_df, how="outer", lsuffix="_local", rsuffix="_remote"
        )
        diff_keys = local_dup_keys + remote_dup_keys
        # remove all cases with duplicated keys
        df = df[~df.index.isin(diff_keys)]
        local_only_keys = df[df[hash_name + "_remote"].isnull()].index.tolist()
        df = df[df[hash_name + "_remote"].notnull()]
        remote_only_keys = df[df[hash_name + "_local"].isnull()].index.tolist()
        df = df[df[hash_name + "_local"].notnull()]
        # no need to drop_duplicates() as each key identifies maximum 1 row in each table
        same_keys = df[
            df[hash_name + "_local"] == df[hash_name + "_remote"]
        ].index.tolist()
        # no need to drop_duplicates() as each key identifies maximum 1 row in each table
        diff_keys += df[
            df[hash_name + "_local"] != df[hash_name + "_remote"]
        ].index.tolist()

        return (
            local_df,
            remote_md5_df,
            same_keys,
            diff_keys,
            local_only_keys,
            remote_only_keys,
        )


def writesync_table(
    engine,
    df_filepath,
    table_name,
    id_name,
    hash_name="hash",
    schema: Optional[str] = None,
    max_records_per_query=None,
    conn_ro=None,
    engine_ro=None,
    drop_cascade: bool = False,
    nb_trials: int = 3,
    logger=None,
):
    """Writes and updates a remote PostgreSQL table from a local CSV table by updating only rows which have been changed.

    Parameters
    ----------
    engine: sqlalchemy connectible
        connection to the PostgreSQL database
    df_filepath: path
        path to the local '.csv', '.csv.zip' or '.parquet' file
    table_name: str
        table name
    id_name: str
        index column name. Assumption is only one column for indexing for now.
    hash_name : str
        hash column name. See :func:`compare_table` for additional assumptions.
    schema: str
        schema name, None means using the default one
    bg_write_csv: bool
        whether to write the updated CSV file in a background thread
    max_records_per_query: int or None
        maximum number of records to be updated in each SQL query. If None, this will be dynamic to make sure each query runs about 5 minute.
    conn_ro: sqlalchemy connectible or None
        read-only connection to the PostgreSQL database. If not specified, it is set to `engine`. This is an old-style keyword argument. It will be replaced by `engine_ro`.
    engine_ro : sqlalchemy.engine.Engine
        read-only connection engine to the server. If not specified, it is set to `engine`. This new keyword argument will replace `conn_ro`.
    drop_cascade : bool
        whether or not to drop using the CASCADE option when dropping a table
    nb_trials: int
        number of read_sql() trials
    logger: logging.Logger or None
        logger for debugging

    Returns
    -------
    df: pandas.DataFrame
        the data frame representing the local table

    Notes
    -----
    The id_name column is written as the primary key of the remote table.

    The function tries to use `conn_ro` instead of `engine` whenever possible to save cost.
    """
    if engine_ro is None:
        if conn_ro is None:
            engine_ro = engine
        else:
            if logger:
                logger.warn(
                    "Keyword argument 'conn_ro' is becoming deprecated. Please replace it 'engine_ro' instead."
                )
            engine_ro = conn_ro
    frame_sql_str = frame_sql(table_name, schema=schema)
    with logger.scoped_debug(
        "Writing table: local '{}' -> remote '{}'".format(df_filepath, frame_sql_str),
        curly=False,
    ) if logger else dummy_scope:
        (
            local_df,
            remote_md5_df,
            same_keys,
            diff_keys,
            local_only_keys,
            remote_only_keys,
        ) = comparesync_table(
            engine_ro,
            df_filepath,
            table_name,
            id_name,
            hash_name=hash_name,
            columns=["*"],
            schema=schema,
            max_records_per_query=max_records_per_query,
            cond=None,
            reading_mode=False,
            nb_trials=nb_trials,
            logger=logger,
        )

        # nothing changed, really!
        if (
            len(diff_keys) == 0
            and len(local_only_keys) == 0
            and len(remote_only_keys) == 0
        ):
            if logger:
                logger.debug(
                    "Both tables are the same and of length {}.".format(len(same_keys))
                )
            return local_df

        if logger:
            logger.debug(
                "Keys: {} to retain, {} to delete, {} to update, {} to write as new.".format(
                    len(same_keys),
                    len(remote_only_keys),
                    len(diff_keys),
                    len(local_only_keys),
                )
            )

        if local_df is None:  # delete remote table if there is no local table
            if logger:
                logger.debug(
                    "Deleting remote table {} if it exists because local table is empty...".format(
                        frame_sql_str
                    )
                )
            query_str = "DROP TABLE IF EXISTS {}{};".format(
                frame_sql_str, " CASCADE" if drop_cascade else ""
            )
            exec_sql(query_str, engine, nb_trials=nb_trials, logger=logger)
            return local_df

        if len(local_df) < 128:  # a small dataset
            to_sql(
                local_df,
                table_name,
                engine,
                schema=schema,
                if_exists="replace",
                nb_trials=nb_trials,
                logger=logger,
            )
            return local_df

        if len(same_keys) == 0:  # no record in the remote table
            if logger:
                logger.debug(
                    "Deleting table {} if it exists since there is no reusable remote record...".format(
                        frame_sql_str
                    )
                )
            query_str = "DROP TABLE IF EXISTS {}{};".format(
                frame_sql_str, " CASCADE" if drop_cascade else ""
            )  # delete the remote table
            exec_sql(query_str, engine, nb_trials=nb_trials, logger=logger)

        record_cap = 128 if max_records_per_query is None else max_records_per_query

        # write those records as new
        if len(local_only_keys) > 0:
            if logger:
                logger.debug("Inserting {} records...".format(len(local_only_keys)))
            with tqdm(total=len(local_only_keys)) as progress_bar:
                df = local_df[local_df.index.isin(local_only_keys)]

                while len(df) > record_cap:
                    df2 = df[:record_cap]
                    df = df[record_cap:]

                    start_time = pd.Timestamp.utcnow()
                    to_sql(
                        df2,
                        table_name,
                        engine,
                        schema=schema,
                        if_exists="append",
                        nb_trials=nb_trials,
                        logger=logger,
                    )
                    # elapsed time is in seconds
                    elapsed_time = (pd.Timestamp.utcnow() - start_time).total_seconds()

                    progress_bar.update(len(df2))

                    if max_records_per_query is None:
                        if elapsed_time > 300:  # too slow
                            record_cap = max(1, record_cap // 2)
                        else:  # too fast
                            record_cap *= 2

                to_sql(
                    df,
                    table_name,
                    engine,
                    schema=schema,
                    if_exists="append",
                    nb_trials=nb_trials,
                    logger=logger,
                )
                progress_bar.update(len(df))

        # remove redundant remote records
        id_list = diff_keys + remote_only_keys
        if len(id_list) > 0 and table_name in list_tables(
            engine_ro, schema=schema, nb_trials=nb_trials, logger=logger
        ):
            if logger:
                logger.debug("Removing {} keys.".format(len(id_list)))
            id_list = ",".join(str(x) for x in id_list)
            query_str = "DELETE FROM {} WHERE {} IN ({});".format(
                frame_sql_str, id_name, id_list
            )
            exec_sql(query_str, engine, nb_trials=nb_trials, logger=logger)

        # insert records that need modification
        if len(diff_keys) > 0:
            if logger:
                logger.debug("Modifying {} records...".format(len(diff_keys)))
            with tqdm(total=len(diff_keys)) as progress_bar:
                df = local_df[local_df.index.isin(diff_keys)]

                while len(df) > record_cap:
                    df2 = df[:record_cap]
                    df = df[record_cap:]

                    start_time = pd.Timestamp.utcnow()
                    to_sql(
                        df2,
                        table_name,
                        engine,
                        schema=schema,
                        if_exists="append",
                        nb_trials=nb_trials,
                        logger=logger,
                    )
                    # elapsed time is in seconds
                    elapsed_time = (pd.Timestamp.utcnow() - start_time).total_seconds()

                    progress_bar.update(len(df2))

                    if max_records_per_query is None:
                        if elapsed_time > 300:  # too slow
                            record_cap = max(1, record_cap // 2)
                        else:  # too fast
                            record_cap *= 2
                to_sql(
                    df,
                    table_name,
                    engine,
                    schema=schema,
                    if_exists="append",
                    nb_trials=nb_trials,
                    logger=logger,
                )
                progress_bar.update(len(df))

    return local_df


def readsync_table(
    engine,
    df_filepath,
    table_name,
    id_name,
    hash_name="hash",
    columns=["*"],
    schema: Optional[str] = None,
    cond=None,
    bg_write_csv=False,
    max_records_per_query=None,
    nb_trials: int = 3,
    logger=None,
    raise_exception_upon_mismatch=True,
):
    """Reads and updates a local CSV table from a PostgreSQL table by updating only rows which have been changed.

    Parameters
    ----------
    engine: sqlalchemy connectible
        connection to the PostgreSQL database
    df_filepath: path
        path to the local '.csv', '.csv.zip' or '.parquet' file
    table_name: str
        table name
    id_name: str
        index column name. Assumption is only one column for indexing for now.
    hash_name : str
        hash column name. See :func:`compare_table` for additional assumptions.
    columns: list
        list of column names the function will read from, ignoring the remaining columns
    schema: str
        schema name, None means using the default one
    cond: str
        additional condition in selecting rows from the PostgreSQL table
    bg_write_csv: bool
        whether to write the updated CSV file in a background thread
    max_records_per_query: int or None
        maximum number of records to be updated in each SQL query. If None, this will be dynamic to make sure each query runs about 5 minute.
    nb_trials: int
        number of read_sql() trials
    logger: logging.Logger or None
        logger for debugging
    raise_exception_upon_mismatch : bool
        whether to raise a RuntimeError upon mismatching the number of hashes and the number of records

    Returns
    -------
    df: pandas.DataFrame
        the data frame representing the read and updated table
    bg: BgInvoke or None, optional
        If bg_write_csv is True, this represents the background thread for writing the updated CSV file. If no background thread is needed, None is returned.
    """
    frame_sql_str = frame_sql(table_name, schema=schema)
    with logger.scoped_debug(
        "Reading table: local '{}' <- remote '{}'".format(df_filepath, frame_sql_str),
        curly=False,
    ) if logger else dummy_scope:
        (
            local_df,
            remote_md5_df,
            same_keys,
            diff_keys,
            local_only_keys,
            remote_only_keys,
        ) = comparesync_table(
            engine,
            df_filepath,
            table_name,
            id_name,
            hash_name=hash_name,
            columns=columns,
            schema=schema,
            max_records_per_query=max_records_per_query,
            cond=cond,
            nb_trials=nb_trials,
            logger=logger,
        )

        # nothing changed, really!
        if (
            len(diff_keys) == 0
            and len(local_only_keys) == 0
            and len(remote_only_keys) == 0
        ):
            if logger:
                logger.debug(
                    "Both tables are the same and of length {}.".format(len(same_keys))
                )
            return (local_df, None) if bg_write_csv else local_df

        if logger:
            logger.debug(
                "Keys: {} to retain, {} to delete, {} to update, {} to read as new.".format(
                    len(same_keys),
                    len(local_only_keys),
                    len(diff_keys),
                    len(remote_only_keys),
                )
            )

        # read remote records
        id_list = diff_keys + remote_only_keys
        if len(id_list) > 0:
            if logger:
                logger.debug("Fetching {} records...".format(len(id_list)))
            with tqdm(total=len(id_list)) as progress_bar:
                column_list = ",".join((table_name + "." + x for x in columns))

                new_md5_df = remote_md5_df[remote_md5_df.index.isin(id_list)]

                record_cap = (
                    128 if max_records_per_query is None else max_records_per_query
                )

                new_dfs = []
                while len(id_list) > 0:
                    if len(id_list) > record_cap:
                        id_list2 = id_list[:record_cap]
                        id_list = id_list[record_cap:]
                    else:
                        id_list2 = id_list
                        id_list = []
                    query_str = "(" + ",".join((str(id) for id in id_list2)) + ")"
                    query_str = "select {} from {} where {} in {}".format(
                        column_list, frame_sql_str, id_name, query_str
                    )
                    if cond is not None:
                        query_str += " and " + cond
                    # if logger:
                    # logger.debug("  using query '{}',".format(query_str))

                    start_time = pd.Timestamp.utcnow()
                    new_dfs.append(
                        read_sql(
                            query_str,
                            engine,
                            index_col=id_name,
                            nb_trials=nb_trials,
                            logger=logger,
                        )
                    )
                    # elapsed time is in seconds
                    elapsed_time = (pd.Timestamp.utcnow() - start_time).total_seconds()

                    progress_bar.update(len(id_list2))

                    if max_records_per_query is None:
                        if elapsed_time > 300:  # too slow
                            record_cap = max(1, record_cap // 2)
                        else:  # too fast
                            record_cap *= 2

            new_df = pd.concat(new_dfs)
            if not hash_name in new_df.columns:
                new_df = new_df.join(new_md5_df)

            if len(new_md5_df) != len(new_df):
                if logger:
                    logger.debug("New dataframe:\n{}".format(str(new_df)))
                    logger.debug("Hash dataframe:\n{}".format(str(new_md5_df)))
                msg = "Something must have gone wrong. Number of hashes {} != number of records {}.".format(
                    len(new_md5_df), len(new_df)
                )
                if raise_exception_upon_mismatch:
                    raise RuntimeError(msg)
                elif logger:
                    logger.warn(msg)
        else:
            new_df = None  # nothing new

        # final df
        if len(same_keys) == 0:
            # former: empty dataframe
            df = local_df[0:0] if new_df is None else new_df
        else:
            local2_df = local_df[local_df.index.isin(same_keys)]
            df = (
                local2_df
                if new_df is None
                else pd.concat([local2_df, new_df], sort=True)
            )
        if new_df is not None:
            df.index = df.index.astype(new_md5_df.index.dtype)
        df = df.groupby(df.index).first().sort_index()

        # write back
        if logger:
            logger.debug("Saving all {} records to file...".format(len(df)))
        if bg_write_csv is True:
            bg = BgInvoke(pd.dfsave, df, df_filepath, index=True)
            return df, bg
        else:
            pd.dfsave(df, df_filepath, index=True)
            return df
