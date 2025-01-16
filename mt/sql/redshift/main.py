"""Useful modules for accessing Redshift"""

import sqlalchemy as sa
from mt import tp, np, pd, logg
from mt.base import LogicError

from ..base import *
from ..psql import compliance_check


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


# ----- functions dealing with sql queries to overcome OperationalError -----


def to_sql(
    df,
    name,
    engine,
    schema: tp.Optional[str] = None,
    if_exists="fail",
    nb_trials: int = 3,
    logger: tp.Optional[logg.IndentedLoggerAdapter] = None,
    **kwargs,
):
    """Writes records stored in a DataFrame to a Redshift database.

    With a number of trials to overcome OperationalError.

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
        what to do when the table exists. Passed as-is to :func:`pandas.DataFrame.to_sql`.
    nb_trials: int
        number of query trials
    logger: mt.logg.IndentedLoggerAdapter, optional
        logger for debugging
    kwargs : dict
        keyword arguments passed as-is to :func:`pandas.DataFrame.to_sql`

    Raises
    ------
    sqlalchemy.exc.ProgrammingError if the local and remote frames do not have the same structure

    Notes
    -----
    The function takes as input a PSQL-compliant dataframe (see `compliance_check()`). It ignores
    any input `index` or `index_label` keyword. Instead, it considers 2 cases. If the dataframe has
    an index or indices, then the tuple of all indices is turned into the primary key. If not,
    there is no primary key and no index is uploaded.

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
    if not table_exists(name, engine, schema=schema):
        if_exists = "replace"
    local_indices = indices(df)

    if local_indices:
        df = df.reset_index(drop=False)
        retval = run_func(
            df.to_sql,
            name,
            engine,
            schema=schema,
            if_exists=if_exists,
            index=False,
            index_label=None,
            nb_trials=nb_trials,
            logger=logger,
            **kwargs,
        )

        if if_exists == "replace":
            query_str = f"ALTER TABLE {frame_sql_str} ADD PRIMARY KEY ({','.join(local_indices)});"
            exec_sql(query_str, engine, nb_trials=nb_trials, logger=logger)
    else:
        retval = run_func(
            df.to_sql,
            name,
            engine,
            schema=schema,
            if_exists=if_exists,
            index=False,
            index_label=None,
            nb_trials=nb_trials,
            logger=logger,
            **kwargs,
        )

    return retval


def conform(
    df: pd.DataFrame,
    table_decl: sa.sql.schema.Table,
) -> pd.DataFrame:
    """Conforms a dataframe to a declarative base so that the columns are properly represented.

    The idea is so that the output dataframe can be used to upload data to a Redshift DB. Primary
    keys and indices are ignored. But whether an integer column is nullable or not is inspected.

    Parameters
    ----------
    df : pandas.DataFrame
        input dataframe
    table_decl : sqlalchemy.sql.schema.Table
        the table declaration to conform to. The output columns are converted where possible to the
        right dtype declared by the base. If you have a declarative base `x`, an instance of
        :class:`sqlalchemy.orm.decl_api.DeclarativeMeta`, you can pass `x.__table__`.

    Returns
    -------
    out_df : pandas.DataFrame
       the output dataframe, where columns of the input dataframe are copied and converted properly
    """

    # extract relevant columns
    columns = [x.name for x in table_decl.columns]
    df = df[columns].copy()

    for x in table_decl.columns:
        try:
            if isinstance(x.type, sa.BigInteger):
                dtype = pd.Int64Dtype() if x.nullable else np.int64
            elif isinstance(x.type, sa.SmallInteger):
                dtype = pd.Int16Dtype() if x.nullable else np.int16
            elif isinstance(x.type, sa.Integer):
                dtype = pd.Int32Dtype() if x.nullable else np.int32
            elif isinstance(x.type, sa.String):
                dtype = str
            elif isinstance(x.type, sa.REAL):
                dtype = np.float32
            elif isinstance(x.type, sa.Float):
                dtype = float
            elif isinstance(x.type, sa.Boolean):
                dtype = pd.BooleanDtype() if x.nullable else np.bool
            elif isinstance(x.type, sa.DateTime):
                dtype = pd.Timestamp
            else:
                raise NotImplementedError(
                    "Unable to conform table declaration '{table_decl.name}' column '{x.name}' with type '{type(x.type)}'."
                )
            if dtype is pd.Timestamp:
                df[x.name] = pd.to_datetime(df[x.name])
            else:
                df[x.name] = df[x.name].astype(dtype)
        except Exception as e:
            raise LogicError(
                "Cannot convert column dtype.",
                debug={"name": x.name, "dtype": dtype},
                causing_error=e,
            )

    return df
