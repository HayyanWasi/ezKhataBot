import atexit
from collections.abc import Iterator
from contextlib import contextmanager

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.core.config import get_settings

_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            get_settings().app_database_url,
            min_size=1,
            max_size=5,
            # prepare_threshold=None: safe behind Supabase's connection pooler
            kwargs={"row_factory": dict_row, "prepare_threshold": None},
            open=True,
        )
        atexit.register(_pool.close)
    return _pool


@contextmanager
def transaction() -> Iterator[Connection]:
    """One database transaction: commits on success, rolls back on any exception."""
    with get_pool().connection() as conn:
        yield conn
