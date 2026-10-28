from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.db import get_session
from app.schemas import PropertyCreate, PropertyRead, PropertyUpdate
from app.services import properties

router = APIRouter(prefix="/properties", tags=["properties"])
SessionDep = Annotated[Session, Depends(get_session)]


@router.post("", response_model=PropertyRead, status_code=status.HTTP_201_CREATED)
def create_property(body: PropertyCreate, session: SessionDep):
    return properties.create_property(session, body)


@router.get("", response_model=list[PropertyRead])
def list_properties(session: SessionDep):
    return properties.list_properties(session)


@router.get("/{property_id}", response_model=PropertyRead)
def get_property(property_id: int, session: SessionDep):
    return properties.get_property(session, property_id)


@router.patch("/{property_id}", response_model=PropertyRead)
def update_property(property_id: int, body: PropertyUpdate, session: SessionDep):
    return properties.update_property(session, property_id, body)


@router.delete("/{property_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_property(property_id: int, session: SessionDep) -> Response:
    properties.delete_property(session, property_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
