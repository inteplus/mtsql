'''Base functions dealing with an sqlite3 file database.'''

from typing import Optional

from mt import pd

from .base import frame_sql, list_tables, exec_sql, read_sql_query


__all__ = ['list_schemas', 'rename_table', 'drop_table', 'rename_column', 'get_table_sql_code', 'list_indices']


def list_schemas(engine, nb_trials: int = 3, logger=None):
    '''Lists all schemas/attached databases of an sqlite engine.

    Parameters
    ----------
    engine : sqlalchemy.engine.Engine
        connection engine to an sqlite3 database
    nb_trials: int
        number of query trials
    logger: logging.Logger or None
        logger for debugging

    Returns
    -------
    pandas.DataFrame
        a dataframe containing columns 'name' and 'file' representing currently attached database
        names and files
    '''
    query_str = 'PRAGMA database_list;'
    return read_sql_query(query_str, engine, nb_trials=nb_trials, logger=logger)


def rename_table(old_table_name, new_table_name, engine, schema: Optional[str] = None, nb_trials: int = 3, logger=None):
    '''Renames a table of a schema.

    Parameters
    ----------
    old_table_name: str
        old table name
    new_table_name: str
        new table name
    engine: sqlalchemy.engine.Engine
        an sqlalchemy connection engine created by function `create_engine()`
    schema: str, optional
        a valid schema name returned from `list_schemas()`
    nb_trials: int
        number of query trials
    logger: logging.Logger or None
        logger for debugging

    Returns
    -------
    whatever exec_sql() returns
    '''
    frame_sql_str = frame_sql(table_name, schema=schema)
    query_str = 'ALTER TABLE {} RENAME TO "{}";'.format(frame_sql_str, new_table_name)
    exec_sql(query_str, engine, nb_trials=nb_trials, logger=logger)


def drop_table(table_name, engine, schema: Optional[str] = None, nb_trials: int = 3, logger=None):
    '''Drops a table if it exists, with restrict or cascade options.

    Parameters
    ----------
    table_name : str
        table name
    engine: sqlalchemy.engine.Engine
        an sqlalchemy connection engine created by function `create_engine()`
    schema: str, optional
        a valid schema name returned from `list_schemas()`
    nb_trials: int
        number of query trials
    logger: logging.Logger or None
        logger for debugging

    Returns
    -------
    whatever exec_sql() returns
    '''
    frame_sql_str = frame_sql(table_name, schema=schema)
    query_str = "DROP TABLE IF EXISTS {};".format(frame_sql_str)
    return exec_sql(query_str, engine, nb_trials=nb_trials, logger=logger)


def rename_column(table_name, old_column_name, new_column_name, engine, schema: Optional[str] = None, nb_trials: int = 3, logger=None):
    '''Renames a column of a table.

    Parameters
    ----------
    table_name: str
        table name
    old_column_name: str
        old column name
    new_column_name: str
        new column name
    engine: sqlalchemy.engine.Engine
        an sqlalchemy connection engine to a sqlite3 database
    schema: str, optional
        a valid schema name returned from `list_schemas()`
    nb_trials: int
        number of query trials
    logger: logging.Logger or None
        logger for debugging
    '''
    frame_sql_str = frame_sql(table_name, schema=schema)
    query_str = 'ALTER TABLE {} RENAME COLUMN {} TO {};'.format(frame_sql_str, old_column_name, new_column_name)
    exec_sql(query_str, engine, nb_trials=nb_trials, logger=logger)


def get_table_sql_code(table_name, engine, nb_trials: int = 3, logger=None):
    '''Gets the SQL string of a table.

    Parameters
    ----------
    table_name: str
        table name
    engine: sqlalchemy.engine.Engine
        an sqlalchemy sqlite3 connection engine created by function `create_engine()`
    nb_trials: int
        number of query trials
    logger: logging.Logger or None
        logger for debugging

    Returns
    -------
    retval: str
        SQL query string defining the table
    '''
    query_str = "SELECT sql FROM sqlite_master WHERE type='table' AND name='{}';".format(table_name)
    return read_sql_query(query_str, engine, nb_trials=nb_trials, logger=logger)['sql'][0]


def list_indices(engine, nb_trials: int = 3, logger=None):
    '''Lists all table indices.

    Parameters
    ----------
    engine: sqlalchemy.engine.Engine
        an sqlalchemy sqlite3 connection engine created by function `create_engine()`
    nb_trials: int
        number of query trials
    logger: logging.Logger or None
        logger for debugging

    Returns
    -------
    index_map : dict
        a `{table_name: index_list}` dictionary mapping each table to a list of indices. Only
        tables with at least one index are listed.
    '''
    query_str = "SELECT name, tbl_name FROM sqlite_master WHERE type='index';"
    df = read_sql_query(query_str, engine, nb_trials=nb_trials, logger=logger)
    res = {}
    for _, row in df.iterrows():
        table_name = row['tbl_name']
        if not table_name in res:
            res[table_name] = []
        index_name = row['name'][len(table_name)+4:]
        res[table_name].append(index_name)
    return res