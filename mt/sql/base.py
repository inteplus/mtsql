'''Base functions dealing with an SQL database.'''

import sqlalchemy as sa
import sqlalchemy.exc as se
import psycopg2 as ps
from mt import pd


__all__ = ['frame_sql', 'run_func', 'read_sql', 'read_sql_query', 'read_sql_table', 'exec_sql', 'to_sql', 'list_schemas', 'list_tables']



def frame_sql(frame_name, schema=None):
    return frame_name if schema is None else '{}.{}'.format(schema, frame_name)


# ----- functions dealing with sql queries to overcome OperationalError -----


def run_func(func, *args, nb_trials=3, logger=None, **kwargs):
    '''Attempt to run a function a number of times to overcome OperationalError exceptions.

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
    '''
    for x in range(nb_trials):
        try:
            return func(*args, **kwargs)
        except (se.ProgrammingError, se.IntegrityError) as e:
            raise
        except (se.DatabaseError, se.OperationalError, ps.OperationalError) as e:
            if logger:
                with logger.scoped_warn("Ignored an exception raised by failed attempt {}/{} to execute `{}.{}()`".format(x+1, nb_trials, func.__module__, func.__name__)):
                    logger.warn_last_exception()
    raise RuntimeError("Attempted {} times to execute `{}.{}()` but failed.".format(
        nb_trials, func.__module__, func.__name__))


def read_sql(sql, conn, index_col=None, set_index_after=False, nb_trials=3, logger=None, **kwargs):
    """Read an SQL query with a number of trials to overcome OperationalError.

    Parameters
    ----------
    index_col: string or list of strings, optional, default: None
        Column(s) to set as index(MultiIndex). See :func:`pandas.read_sql`.
    set_index_after: bool
        whether to set index specified by index_col via the pandas.read_sql() function or after the function has been invoked
    nb_trials: int
        number of query trials
    logger: logging.Logger or None
        logger for debugging
    kwargs: dict
        other keyword arguments to be passed directly to :func:`pandas.read_sql`

    See Also
    --------
    pandas.read_sql
    """
    if index_col is None or not set_index_after:
        return run_func(pd.read_sql, sql, conn, index_col=index_col, nb_trials=nb_trials, logger=logger, **kwargs)
    df = run_func(pd.read_sql, sql, conn,
                  nb_trials=nb_trials, logger=logger, **kwargs)
    return df.set_index(index_col, drop=True)


def read_sql_query(sql, conn, index_col=None, set_index_after=False, nb_trials=3, logger=None, **kwargs):
    """Read an SQL query with a number of trials to overcome OperationalError.

    Parameters
    ----------
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
        return run_func(pd.read_sql_query, sql, conn, index_col=index_col, nb_trials=nb_trials, logger=logger, **kwargs)
    df = run_func(pd.read_sql_query, sql, conn,
                  nb_trials=nb_trials, logger=logger, **kwargs)
    return df.set_index(index_col, drop=True)


def read_sql_table(table_name, conn, nb_trials=3, logger=None, **kwargs):
    """Read an SQL table with a number of trials to overcome OperationalError.

    Parameters
    ----------
    nb_trials: int
        number of query trials
    logger: logging.Logger or None
        logger for debugging

    See Also
    --------
    pandas.read_sql_table

    """
    return run_func(pd.read_sql_table, table_name, conn, nb_trials=nb_trials, logger=logger, **kwargs)


def exec_sql(sql, conn, *args, nb_trials=3, logger=None, **kwargs):
    """Execute an SQL query with a number of trials to overcome OperationalError. See sqlalchemy.Engine.execute() for more details.

    Parameters
    ----------
    nb_trials: int
        number of query trials
    logger: logging.Logger or None
        logger for debugging

    """
    return run_func(conn.execute, sql, *args, nb_trials=nb_trials, logger=logger, **kwargs)


def to_sql(df, name, conn, schema=None, if_exists='fail', nb_trials=3, logger=None, **kwargs):
    """Writes records stored in a DataFrame to an SQL database, with a number of trials to overcome OperationalError.

    Parameters
    ----------
    df: pandas.DataFrame
        dataframe to be sent to the server
    conn: sqlalchemy.engine.Engine or sqlite3.Connection
        the connection engine
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
        if 'index' in kwargs:
            raise ValueError(
                "The `mt.sql.psql.to_sql()` function does not accept `index` as a keyword.")
        if 'index_label' in kwargs:
            raise ValueError(
                "This `mt.sql.psql.to_sql()` function does not accept `index_label` as a keyword.")

    compliance_check(df)
    frame_sql_str = frame_sql(name, schema=schema)

    # if the remote frame does not exist, force `if_exists` to 'replace'
    if not frame_exists(name, conn, schema=schema, nb_trials=nb_trials, logger=logger):
        if_exists = 'replace'
    local_indices = indices(df)

    # not 'gently replace' case
    if if_exists != 'gently_replace':
        if not local_indices:
            return run_func(df.to_sql, name, conn, schema=schema, if_exists=if_exists, index=False, index_label=None, nb_trials=nb_trials, logger=logger, **kwargs)
        retval = run_func(df.to_sql, name, conn, schema=schema, if_exists=if_exists,
                          index=True, index_label=None, nb_trials=nb_trials, logger=logger, **kwargs)
        if if_exists == 'replace':
            exec_sql("ALTER TABLE {} ADD PRIMARY KEY ({});".format(frame_sql_str, ','.join(
                local_indices)), conn, nb_trials=nb_trials, logger=logger)
        return retval

    # the remaining section is the 'gently replace' case

    # remote indices
    remote_indices = list_primary_columns(
        name, conn, schema=schema, nb_trials=nb_trials, logger=logger)
    if local_indices != remote_indices:
        raise _se.ProgrammingError("SELECT * FROM {} LIMIT 1;".format(frame_sql_str), remote_indices,
                                   "Remote index '{}' differs from local index '{}'.".format(remote_indices, local_indices))

    # remote columns
    remote_columns = list_columns(
        name, conn, schema=schema, nb_trials=nb_trials, logger=logger)
    remote_columns = [x for x in remote_columns if not x in remote_indices]
    columns = list(df.columns)
    if columns != remote_columns:
        raise _se.ProgrammingError("SELECT * FROM {} LIMIT 1;".format(frame_sql_str), "matching non-primary fields",
                                   "Local columns '{}' differ from remote columns '{}'.".format(columns, remote_columns))

    exec_sql("DELETE FROM {};".format(frame_sql_str),
             conn, nb_trials=nb_trials, logger=logger)
    return run_func(df.to_sql, name, conn, schema=schema, if_exists='append', index=bool(local_indices), index_label=None, nb_trials=nb_trials, logger=logger, **kwargs)


# ----- functions navigating the database -----


def list_schemas(conn, nb_trials=3, logger=None):
    '''Lists all schemas.

    Parameters
    ----------
        conn : sqlalchemy.engine.base.Engine
            an sqlalchemy connection engine created by function `create_engine()`
        nb_trials: int
            number of query trials
        logger: logging.Logger or None
            logger for debugging

    Returns
    -------
        out : list
            list of all schema names
    '''
    return run_func(sa.inspect, conn, nb_trials=nb_trials, logger=logger).get_schemas()


def list_tables(conn, schema=None, nb_trials=3, logger=None):
    '''Lists all tables of a given schema.

    Parameters
    ----------
        conn : sqlalchemy.engine.base.Engine
            an sqlalchemy connection engine created by function :func:`sqlalchemy.create_engine`
        schema : str or None
            a valid schema name returned from :func:`list_schemas`. Default to sqlalchemy
        nb_trials: int
            number of query trials
        logger: logging.Logger or None
            logger for debugging

    Returns
    -------
        out : list
            list of all table names
    '''
    return run_func(conn.table_names, schema=schema, nb_trials=nb_trials, logger=logger)
