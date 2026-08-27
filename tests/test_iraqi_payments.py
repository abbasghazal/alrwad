import pytest
from fastapi import HTTPException

from services.iraqi_payments import normalize_iraqi_phone, validate_payment_method


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("07801234567", "+9647801234567"),
        ("+9647801234567", "+9647801234567"),
        ("009647801234567", "+9647801234567"),
        ("0770 123 4567", "+9647701234567"),
    ],
)
def test_normalize_iraqi_phone(raw, expected):
    assert normalize_iraqi_phone(raw) == expected


@pytest.mark.parametrize("raw", ["12345", "06123456789", "+971501234567"])
def test_normalize_iraqi_phone_rejects_invalid_numbers(raw):
    with pytest.raises(HTTPException):
        normalize_iraqi_phone(raw)


def test_validate_payment_method_accepts_zain_cash():
    assert validate_payment_method("zain_cash")["name"] == "Zain Cash"


def test_validate_payment_method_rejects_unknown_method():
    with pytest.raises(HTTPException):
        validate_payment_method("unknown")
