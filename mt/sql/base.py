"""Base functions dealing with an SQL database."""

import re
import uuid
import sqlalchemy as sa
import sqlalchemy.exc as se
import psycopg as ps

from mt import tp, logg, pd, ctx, halo


__all__ = [
    "frame_sql",
    "indices",
    "run_func",
    "conn_ctx",
    "engine_execute",
    "read_sql",
    "read_sql_table",
    "exec_sql",
    "list_schemas",
    "list_tables",
    "list_views",
    "table_exists",
    "create_temp_id_table",
    "temp_table_name",
    "temp_table_find_new_id",
    "temp_table_drop",
    "to_temp_table",
]


def frame_sql(frame_name, schema: tp.Optional[str] = None):
    return frame_name if schema is None else "{}.{}".format(schema, frame_name)


def indices(df):
    """Returns the list of named indices of the dataframe, ignoring any unnamed index."""
    a = list(df.index.names)
    return a if a != [None] else []


# ----- functions dealing with sql queries to overcome OperationalError -----


def run_func(
    func,
    *args,
    nb_trials: int = 3,
    logger: tp.Optional[logg.IndentedLoggerAdapter] = None,
    **kwargs,
):
    """Attempt to run a function a number of times to overcome OperationalError exceptions.

    Parameters
    ----------
    func: function
        function to be invoked
    args: sequence
        arguments to be passed to the function
    nb_trials: int
        number of query trials
    logger: mt.logg.IndentedLoggerAdapter, optional
        logger for debugging
    kwargs: dict
        keyword arguments to be passed to the function
    """
    for x in range(nb_trials):
        try:
            return func(*args, **kwargs)
        except (se.ProgrammingError, se.IntegrityError):
            raise
        except (
            se.DatabaseError,
            se.OperationalError,
            ps.OperationalError,
            se.InterfaceError,
            se.PendingRollbackError,
        ):
            if logger:
                msg = f"Ignored an exception raised by failed attempt {x+1}/{nb_trials} to execute `{func.__module__}.{func.__name__}()`"
                with logger.scoped_warn(msg):
                    logger.warn_last_exception()
    raise RuntimeError(
        f"Attempted {nb_trials} times to execute `{func.__module__}.{func.__name__}` but failed."
    )


def conn_ctx(engine):
    if isinstance(engine, sa.engine.Engine):
        return engine.begin()
    return ctx.nullcontext(engine)


def engine_execute(engine, sql, *args, **kwargs):
    text_sql = sa.text(sql) if isinstance(sql, str) else sql
    with conn_ctx(engine) as conn:
        return conn.execute(text_sql, *args, **kwargs)


def trim_sql_query(sql_query: str) -> str:
    sql_query = " ".join(sql_query.splitlines())
    sql_query = " ".join(sql_query.split())
    return sql_query


def read_sql(
    sql,
    engine,
    index_col: tp.Union[str, tp.List[str], None] = None,
    chunksize: tp.Optional[int] = None,
    nb_trials: int = 3,
    exception_handling: str = "raise",
    logger: tp.Optional[logg.IndentedLoggerAdapter] = None,
    **kwargs,
) -> pd.DataFrame:
    """Read an SQL query with a number of trials to overcome OperationalError.

    The function wraps :func:`pandas.read_sql_query`. However, when `chunksize` is not None, it
    iterates over chunks and concatenates them. In addition, if `logger` is not None, a progress
    bar is shown in that case.

    A dataframe is always returned.

    Parameters
    ----------
    sql : str or object
        SQL query to be executed. The query can be a string or an sqlalchemy object that can be
        used for querying. Passed as-is to :func:`pandas.read_sql_query`.
    engine : sqlalchemy.engine.Engine
        connection engine to the server
    index_col: string or list of strings, optional, default: None
        Column(s) to set as index(MultiIndex). Passed as-is to :func:`pandas.read_sql_query`.
    chunksize : int, default None
        If specified, iteratively reads a number of `chunksize` rows. In this case, a progress bar
        is also shown if `logger` is provided.
    nb_trials: int
        number of query trials. If `chunksize` is provided, this is only effective before an
        iterator is returned from pandas.
    exception_handling : {'warn', 'raise'}
        policy for handling SQL-raised exceptions when iterating over many chunks to completely
        download the result. Only valid when `chunksize` is provided. Right now there are only
        2 policies. Either to raise the exception as-is ('raise'), or to raise the exception as a
        warning ('warn') and return whatever has been downloaded.
    logger: mt.logg.IndentedLoggerAdapter, optional
        logger for debugging
    kwargs: dict
        other keyword arguments to be passed directly to :func:`pandas.read_sql_query`

    Returns
    -------
    pandas.DataFrame
        the output dataframe

    See Also
    --------
    pandas.read_sql_query
    """

    if isinstance(sql, str):
        text_sql = sql
        sql = sa.text(text_sql)
    else:
        text_sql = str(sql.compile(compile_kwargs={"literal_binds": True}))
    text_sql = trim_sql_query(text_sql)

    if chunksize is not None:
        s = "read_sql: '{}'".format(text_sql)
        spinner = halo.Halo(s, spinner="dots", enabled=bool(logger))
        spinner.start()
        ts = pd.Timestamp.now()
        cnt = 0

    with conn_ctx(engine) as conn:
        res = run_func(
            pd.read_sql,
            sql,
            conn,
            index_col=index_col,
            chunksize=chunksize,
            nb_trials=nb_trials,
            logger=logger,
            **kwargs,
        )

    if chunksize is None:
        return res

    try:
        dfs = []
        for df in res:
            dfs.append(df)
            cnt += len(df)
            td = (pd.Timestamp.now() - ts).total_seconds() + 0.001
            s = "{} rows ({} rows/sec)".format(cnt, cnt / td)
            spinner.text = s
        df = pd.concat(dfs)
        s = "{} rows".format(cnt)
        spinner.succeed(s)
    except:
        s = "{} rows".format(cnt)
        spinner.fail(s)
        if logger:
            logger.warn_last_exception()
        if exception_handling == "raise":
            raise
        if exception_handling != "warn":
            raise ValueError(
                "Unknown value for argument 'exception_handling': '{}'.".format(
                    exception_handling
                )
            )
        df = pd.concat(dfs)

    return df


def read_sql_table(
    table_name,
    engine,
    nb_trials: int = 3,
    logger: tp.Optional[logg.IndentedLoggerAdapter] = None,
    **kwargs,
):
    """Read an SQL table with a number of trials to overcome OperationalError.

    Parameters
    ----------
    table_name : str
        name of the table to be read
    engine : sqlalchemy.engine.Engine
        connection engine to the server
    nb_trials: int
        number of query trials
    logger: mt.logg.IndentedLoggerAdapter, optional
        logger for debugging

    See Also
    --------
    pandas.read_sql_table

    """
    return run_func(
        pd.read_sql_table,
        table_name,
        engine,
        nb_trials=nb_trials,
        logger=logger,
        **kwargs,
    )


def exec_sql(
    sql,
    engine,
    *args,
    nb_trials: int = 3,
    logger: tp.Optional[logg.IndentedLoggerAdapter] = None,
    **kwargs,
):
    """Execute an SQL query with a number of trials to overcome OperationalError.

    Parameters
    ----------
    sql : str
        SQL query to be executed
    engine : sqlalchemy.engine.Engine
        connection engine to the server
    args : list
        positional arguments to be passed as-is to :func:`sqlalchemy.engine.Engine.execute`
    nb_trials: int
        number of query trials
    logger: mt.logg.IndentedLoggerAdapter, optional
        logger for debugging

    See Also
    --------
    sqlalchemy.engine.Engine.execute
        for more details
    """

    return run_func(
        engine_execute, engine, sql, *args, nb_trials=nb_trials, logger=logger, **kwargs
    )


# ----- functions navigating the database -----


def list_schemas(engine):
    """Lists all schemas.

    Parameters
    ----------
    engine : sqlalchemy.engine.Engine
        connection engine to the server

    Returns
    -------
    list
        list of all schema names
    """
    return sa.inspect(engine).get_schema_names()


def list_tables(engine, schema: tp.Optional[str] = None):
    """Lists all tables of a given schema.

    Parameters
    ----------
    engine : sqlalchemy.engine.Engine
        connection engine to the server
    schema: str, optional
        a valid schema name returned from :func:`list_schemas`. Default to sqlalchemy

    Returns
    -------
    list
        list of all table names
    """
    return sa.inspect(engine).get_table_names(schema=schema)


def list_views(engine, schema: tp.Optional[str] = None):
    """Lists all views of a given schema.

    Parameters
    ----------
    engine : sqlalchemy.engine.Engine
        connection engine to the server
    schema: str, optional
        a valid schema name returned from :func:`list_schemas`. Default to sqlalchemy

    Returns
    -------
    list
        list of all view names
    """
    return sa.inspect(engine).get_view_names(schema=schema)


def table_exists(
    table_name,
    engine,
    schema: tp.Optional[str] = None,
):
    """Checks if a table exists.

    Parameters
    ----------
    table_name: str
        name of table
    engine: sqlalchemy.engine.Engine
        an sqlalchemy connection engine created by function `create_engine()`
    schema: str or None
        a valid schema name returned from `list_schemas()`

    Returns
    -------
    retval: bool
        whether a table or a view exists with the given name
    """

    return sa.inspect(engine).has_table(table_name, schema=schema)


def create_temp_id_table(
    l_ids: list,
    conn: sa.engine.Connection,
    int_type="int",
    chunksize: int = 1000000,
) -> str:
    """Creates a temporary table to containing a list of ids.

    Parameters
    ----------
    l_ids : list
        list of ids to be inserted into the table
    conn : sqlalchemy.engine.Connection
        a connection that has been opened
    int_type : str
        an SQL string representing the int type
    chunksize : int
        maximum number of ids to be inserted in each INSERT statement

    Returns
    -------
    table_name : str
        name of the temporary table. The table will be deleted at the end of the connection
    """

    table_name = f"tab_{uuid.uuid4().hex}"

    query_str = f"CREATE TEMP TABLE {table_name}(id {int_type});"
    conn.execute(sa.text(query_str))

    while True:
        l_ids2 = l_ids[:chunksize]
        if len(l_ids2) == 0:
            break

        values = ",".join((f"({id})" for id in l_ids2))
        query_str = f"INSERT INTO {table_name}(id) VALUES {values};"
        conn.execute(sa.text(query_str))
        l_ids = l_ids[chunksize:]

    return table_name


def temp_table_name(id: int) -> str:
    """Converts a temp table id into a temp table name."""
    return f"mttmp_{id}"


def temp_table_find_new_id(engine: sa.engine.Engine) -> int:
    """Finds a new temp table id that does not exist in the public schema.

    Parameters
    ----------
    engine : sqlalchemy.engine.Engine
        connection engine to the server

    Returns
    -------
    id : int
        table id that has not been existent in the public schema.
    """
    l_tableNames = list_tables(engine)
    max_id = -1
    for table_name in l_tableNames:
        s = re.match(r"mttmp_(\d+)", table_name)
        if s:
            id = int(s[1])
            if max_id < id:
                max_id = id
    return max_id + 1


def temp_table_drop(
    engine: sa.engine.Engine,
    id: int,
):
    """Drops a temp table.

    Parameters
    ----------
    id : int or str
        table id or table name. An id can be generated by invoking :func:`temp_table_find_new_id`.
    engine : sqlalchemy.engine.Engine
        connection engine to the server
    """

    name = id if isinstance(id, str) else temp_table_name(id)
    sql = f"DROP TABLE IF EXISTS {name}"
    return engine_execute(engine, sql)


@ctx.contextmanager
def to_temp_table(df: pd.DataFrame, engine: sa.engine.Engine, **kwds):
    """
    A context manager that uploads a dataframe to a temp table and cleans up the table when done.

    You can use the class in a with statement to work with the temp table, whose name is returned
    as the context manager object.

    Parameters
    ----------
    df : pandas.DataFrame
        dataframe to be uploaded to the database as a temporary table
    engine : sqlalchemy.engine.Engine
        engine connrecting to the database
    **kwds : dict
        other keyword arguments passed as-is to :func:`pandas.DataFrame.to_sql`
    """

    tid = temp_table_find_new_id(engine)
    name = temp_table_name(tid)
    try:
        df.to_sql(name, engine, **kwds)
        yield name
    finally:
        temp_table_drop(engine, tid)
