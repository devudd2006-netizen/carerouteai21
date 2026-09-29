"""CareRoute AI — database setup.

Production uses PostgreSQL (set DATABASE_URL, e.g. postgresql+psycopg://user:pw@host/db).
The prototype defaults to a local SQLite file so the demo runs with zero external services.
"""
import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "sqlite:///./careroute.db",
)

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=_connect_args, future=True)

if DATABASE_URL.startswith("sqlite"):
    # SQLite safety net: enable WAL + a busy timeout so concurrent role dashboards
    # (e.g. the 3s /sync poller alongside emergency writes) never fail with
    # "database is locked". PostgreSQL is unaffected by this block.
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
