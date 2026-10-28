from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Payment
from app.schemas import PaymentCreate
from app.services import leases
from app.services.errors import RuleViolationError


def create_payment(session: Session, lease_id: int, data: PaymentCreate, today: date) -> Payment:
    # Ended leases still accept payments, e.g. arrears after move-out (HLD decision P1).
    leases.get_lease(session, lease_id)
    if data.paid_on > today:
        raise RuleViolationError("paid_on", "paid_on cannot be in the future")  # decision P2
    payment = Payment(lease_id=lease_id, **data.model_dump())
    session.add(payment)
    session.commit()
    session.refresh(payment)
    return payment


def list_payments(session: Session, lease_id: int) -> list[Payment]:
    leases.get_lease(session, lease_id)
    query = (
        select(Payment).where(Payment.lease_id == lease_id).order_by(Payment.paid_on, Payment.id)
    )
    return list(session.scalars(query))
