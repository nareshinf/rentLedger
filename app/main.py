from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from app.db import get_database_url, make_engine, make_session_factory
from app.errors import validation_exception_handler
from app.routers import health


def create_app(database_url: str | None = None) -> FastAPI:
    app = FastAPI(title="RentLedger")
    app.state.engine = make_engine(database_url or get_database_url())
    app.state.session_factory = make_session_factory(app.state.engine)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.include_router(health.router)
    return app


app = create_app()
