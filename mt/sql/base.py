"""Base functions dealing with an SQL database."""

import typing as tp

import sqlalchemy as sa
import sqlalchemy.exc as se
import psycopg2 as ps
from halo import Halo

from mt import pd


__all__ = [
    "frame_sql",
    "run_func",
    "read_sql",
    "read_sql_query",
    "read_sql_table",
    "exec_sql",
    "list_schemas",
    "list_tables",
]


def frame_sql(frame_name, schema: tp.Optional[str] = None):
    return frame_name if schema is None else "{}.{}".format(schema, frame_name)


# ----- functions dealing with sql queries to overcome OperationalError -----


def run_func(func, *args, nb_trials: int = 3, logger=None, **kwargs):
    """Attempt to run a function a number of times to overcome OperationalError exceptions.

    Parameters
    ----------
    func: function
        function to be invoked
    args: sequence
        arguments to be passed to the function
    nb_trials: int
        number of query trials
    logger: logging.Logger or None
        logger for debugging
    kwargs: dict
        keyword arguments to be passed to the function
    """
    for x in range(nb_trials):
        try:
            return func(*args, **kwargs)
        except (se.ProgrammingError, se.IntegrityError) as e:
            raise
        except (se.DatabaseError, se.OperationalError, ps.OperationalError) as e:
            if logger:
                with logger.scoped_warn(
                    "Ignored an exception raised by failed attempt {}/{} to execute `{}.{}()`".format(
                        x + 1, nb_trials, func.__module__, func.__name__
                    )
                ):
                    logger.warn_last_exception()
    raise RuntimeError(
        "Attempted {} times to execute `{}.{}()` but failed.".format(
            nb_trials, func.__module__, func.__name__
        )
    )


def read_sql(
    sql,
    engine,
    index_col: tp.Union[str, tp.List[str], None] = None,
    chunksize: tp.Optional[int] = None,
    nb_trials: int = 3,
    exception_handling: str = "raise",
    logger=None,
    **kwargs
) -> pd.DataFrame:
    """Read an SQL query with a number of trials to overcome OperationalError.

    The function wraps :func:`pandas.read_sql`. However, when `chunksize` is not None, it iterates
    over chunks and concatenate them. In addition, if `logger` is not None, a progress bar is shown
    in that case.

    A dataframe is always returned.

    Parameters
    ----------
    sql : str
        SQL query to be executed
    engine : sqlalchemy.engine.Engine
        connection engine to the server
    index_col: string or list of strings, optional, default: None
        Column(s) to set as index(MultiIndex). Passed as-is to :func:`pandas.read_sql`.
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
    logger: logging.Logger or None
        logger for debugging
    kwargs: dict
        other keyword arguments to be passed directly to :func:`pandas.read_sql`

    Returns
    -------
    pandas.DataFrame
        the output dataframe

    See Also
    --------
    pandas.read_sql
    """

    if chunksize is not None:
        s = "read_sql: '{}'".format(sql)
        spinner = Halo(s, spinner="dots", enabled=bool(logger))
        spinner.start()
        ts = pd.Timestamp.now()
        cnt = 0

    res = run_func(
        pd.read_sql,
        sql,
        engine,
        index_col=index_col,
        chunksize=chunksize,
        nb_trials=nb_trials,
        logger=logger,
        **kwargs
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


def read_sql_query(
    sql,
    engine,
    index_col=None,
    set_index_after=False,
    nb_trials: int = 3,
    logger=None,
    **kwargs
):
    """Read an SQL query with a number of trials to overcome OperationalError.

    Parameters
    ----------
    sql : str
        SQL query to be executed
    engine : sqlalchemy.engine.Engine
        connection engine to the server
    index_col: string or list of strings, optional, default: None
        Column(s) to set as index(MultiIndex). See :func:`pandas.read_sql_query`.
    set_index_after: bool
        whether to set index specified by index_col via the pandas.read_sql_query() function or after the function has been invoked
    nb_trials: int
        number of query trials
    logger: logging.Logger or None
        logger for debugging
    kwargs: dict
        other keyword arguments to be passed directly to :func:`pandas.read_sql_query`

    See Also
    --------
    pandas.read_sql_query
    """
    if index_col is None or not set_index_after:
        return run_func(
            pd.read_sql_query,
            sql,
            engine,
            index_col=index_col,
            nb_trials=nb_trials,
            logger=logger,
            **kwargs
        )
    df = run_func(
        pd.read_sql_query, sql, engine, nb_trials=nb_trials, logger=logger, **kwargs
    )
    return df.set_index(index_col, drop=True)


def read_sql_table(table_name, engine, nb_trials: int = 3, logger=None, **kwargs):
    """Read an SQL table with a number of trials to overcome OperationalError.

    Parameters
    ----------
    table_name : str
        name of the table to be read
    engine : sqlalchemy.engine.Engine
        connection engine to the server
    nb_trials: int
        number of query trials
    logger: logging.Logger or None
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
        **kwargs
    )


def exec_sql(sql, engine, *args, nb_trials: int = 3, logger=None, **kwargs):
    """Execute an SQL query with a number of trials to overcome OperationalError. See :func:`sqlalchemy.engine.Engine.execute` for more details.

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
    logger: logging.Logger or None
        logger for debugging

    """
    return run_func(
        engine.execute, sql, *args, nb_trials=nb_trials, logger=logger, **kwargs
    )


# ----- functions navigating the database -----


def list_schemas(engine, nb_trials: int = 3, logger=None):
    """Lists all schemas.

    Parameters
    ----------
    engine : sqlalchemy.engine.Engine
        connection engine to the server
    nb_trials: int
        number of query trials
    logger: logging.Logger or None
        logger for debugging

    Returns
    -------
    list
        list of all schema names
    """
    return run_func(
        sa.inspect, engine, nb_trials=nb_trials, logger=logger
    ).get_schemas()


def list_tables(
    engine, schema: tp.Optional[str] = None, nb_trials: int = 3, logger=None
):
    """Lists all tables of a given schema.

    Parameters
    ----------
    engine : sqlalchemy.engine.Engine
        connection engine to the server
    schema: str, optional
        a valid schema name returned from :func:`list_schemas`. Default to sqlalchemy
    nb_trials: int
        number of query trials
    logger: logging.Logger or None
        logger for debugging

    Returns
    -------
    list
        list of all table names
    """
    return run_func(
        engine.table_names, schema=schema, nb_trials=nb_trials, logger=logger
    )
