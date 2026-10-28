import os
from collections.abc import Iterator, Mapping

from fastapi import Request
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DEFAULT_DATABASE_URL = "sqlite:///./rentledger.db"
DATABASE_URL_ENV = "RENTLEDGER_DATABASE_URL"


def get_database_url(environ: Mapping[str, str] = os.environ) -> str:
    return environ.get(DATABASE_URL_ENV, DEFAULT_DATABASE_URL)


def make_engine(url: str) -> Engine:
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_session(request: Request) -> Iterator[Session]:
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()
