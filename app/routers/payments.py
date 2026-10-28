from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db import get_session
from app.schemas import BalanceRead, PaymentCreate, PaymentRead
from app.services import balance, payments
from app.services.clock import Clock, get_clock

router = APIRouter(prefix="/leases", tags=["payments"])
SessionDep = Annotated[Session, Depends(get_session)]
ClockDep = Annotated[Clock, Depends(get_clock)]


@router.post(
    "/{lease_id}/payments", response_model=PaymentRead, status_code=status.HTTP_201_CREATED
)
def create_payment(lease_id: int, body: PaymentCreate, session: SessionDep, clock: ClockDep):
    return payments.create_payment(session, lease_id, body, today=clock.today())


@router.get("/{lease_id}/payments", response_model=list[PaymentRead])
def list_payments(lease_id: int, session: SessionDep):
    return payments.list_payments(session, lease_id)


@router.get("/{lease_id}/balance", response_model=BalanceRead)
def get_balance(
    lease_id: int,
    session: SessionDep,
    clock: ClockDep,
    as_of: Annotated[date | None, Query(alias="asOf")] = None,
):
    return balance.compute_balance(session, lease_id, as_of or clock.today())
