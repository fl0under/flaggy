"""
Database connection and utilities for flaggy
"""
import psycopg
from contextlib import contextmanager
from typing import Generator

from ctf_solver.config import DB_DSN


def get_db_connection():
    """Get a database connection using the configured DSN"""
    return psycopg.connect(DB_DSN)


@contextmanager
def get_db_cursor() -> Generator[psycopg.Cursor, None, None]:
    """Context manager for database operations"""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
    finally:
        conn.close()


# Legacy DB class for backward compatibility
class DB:
    def __init__(self, dsn: str):
        self.dsn = dsn

    def get_conn(self):
        return get_db_connection()

    def put_conn(self, conn):
        if conn:
            conn.close()


