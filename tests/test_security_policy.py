import pytest
from fastapi import HTTPException

from security.password_policy import validate_password_strength


def test_password_policy_accepts_strong_password():
    validate_password_strength("Strong123")


@pytest.mark.parametrize("password", ["short1A", "lowercase1", "UPPERCASE1", "NoDigitsHere"])
def test_password_policy_rejects_weak_passwords(password):
    with pytest.raises(HTTPException):
        validate_password_strength(password)
