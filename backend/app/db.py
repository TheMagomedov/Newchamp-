from contextlib import contextmanager
from sqlalchemy import create_engine, MetaData, text
from sqlalchemy.engine import URL
from .config import odbc

engine = create_engine(URL.create('mssql+pyodbc', query={'odbc_connect': odbc()}), pool_pre_ping=True, pool_size=10, max_overflow=20)
metadata = MetaData(schema='dbo')

def reflect():
    if not metadata.tables:
        metadata.reflect(bind=engine)
        for table in metadata.tables.values():
            table.implicit_returning = False  # SQL Server OUTPUT is incompatible with enabled triggers.

def table(name):
    reflect()
    return metadata.tables['dbo.' + name]

@contextmanager
def transaction(actor=None):
    with engine.begin() as conn:
        conn.execute(text("EXEC sys.sp_set_session_context @key=N'ActorId', @value=:actor"), {'actor': actor})
        try:
            yield conn
        finally:
            # Pool reuse must never inherit a previous user's audit identity.
            try:
                conn.execute(text("EXEC sys.sp_set_session_context @key=N'ActorId', @value=NULL"))
            except Exception:
                pass  # Failed transactions are rolled back by engine.begin().

