from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from app.db import create_tables, get_database_url, make_engine, make_session_factory
from app.errors import conflict_handler, not_found_handler, validation_exception_handler
from app.routers import health, properties, tenants
from app.services.errors import ConflictError, NotFoundError


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    create_tables(app.state.engine)
    yield


def create_app(database_url: str | None = None) -> FastAPI:
    app = FastAPI(title="RentLedger", lifespan=lifespan)
    app.state.engine = make_engine(database_url or get_database_url())
    app.state.session_factory = make_session_factory(app.state.engine)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(NotFoundError, not_found_handler)
    app.add_exception_handler(ConflictError, conflict_handler)
    app.include_router(health.router)
    app.include_router(properties.router)
    app.include_router(tenants.router)
    return app


app = create_app()
