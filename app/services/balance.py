from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Payment
from app.services import leases
from app.services.rent import due_dates

CENT = Decimal("0.01")


@dataclass(frozen=True)
class Balance:
    lease_id: int
    as_of: date
    monthly_rent: Decimal
    charges_due: int
    charged: Decimal
    paid: Decimal
    balance: Decimal


def compute_balance(session: Session, lease_id: int, as_of: date) -> Balance:
    lease = leases.get_lease(session, lease_id)
    charges_due = len(due_dates(lease.start_date, lease.end_date, lease.due_day, through=as_of))
    charged = (lease.monthly_rent * charges_due).quantize(CENT)

    # Sum in Python over Decimal values: SQL SUM() on SQLite would add floats.
    amounts = session.scalars(
        select(Payment.amount).where(Payment.lease_id == lease_id, Payment.paid_on <= as_of)
    )
    paid = sum(amounts, Decimal("0")).quantize(CENT)

    return Balance(
        lease_id=lease.id,
        as_of=as_of,
        monthly_rent=lease.monthly_rent,
        charges_due=charges_due,
        charged=charged,
        paid=paid,
        balance=(charged - paid).quantize(CENT),
    )
