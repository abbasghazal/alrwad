import pytest
from fastapi import HTTPException

from services.payments import ensure_positive_amount, require_booking_payment_match


class DummyBooking:
    def __init__(self, price=25.0, status="confirmed", payment_status="pending"):
        self.price = price
        self.status = status
        self.payment_status = payment_status


def test_ensure_positive_amount_accepts_positive_value():
    ensure_positive_amount(1)


@pytest.mark.parametrize("amount", [0, -1])
def test_ensure_positive_amount_rejects_zero_or_negative(amount):
    with pytest.raises(HTTPException):
        ensure_positive_amount(amount)


def test_booking_payment_match_accepts_exact_booking_price():
    require_booking_payment_match(DummyBooking(price=25), 25)


def test_booking_payment_match_rejects_wrong_amount():
    with pytest.raises(HTTPException):
        require_booking_payment_match(DummyBooking(price=25), 20)


def test_booking_payment_match_rejects_paid_booking():
    with pytest.raises(HTTPException):
        require_booking_payment_match(DummyBooking(payment_status="paid"), 25)


def test_booking_payment_match_rejects_inactive_booking():
    with pytest.raises(HTTPException):
        require_booking_payment_match(DummyBooking(status="cancelled"), 25)
