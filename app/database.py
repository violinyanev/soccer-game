import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DB_PATH = os.getenv("DB_PATH", "/app/data/db.sqlite")
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    # Import models so Base knows about them before create_all
    import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    _migrate()


def _migrate():
    """Lightweight, idempotent schema migrations for existing databases.

    create_all() never alters existing tables, so add columns introduced after
    the first deploy by hand. Safe to run on every startup.
    """
    with engine.begin() as conn:
        cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(predictions)")}
        if "predicted_home" not in cols:
            conn.exec_driver_sql("ALTER TABLE predictions ADD COLUMN predicted_home INTEGER")
        if "predicted_away" not in cols:
            conn.exec_driver_sql("ALTER TABLE predictions ADD COLUMN predicted_away INTEGER")
