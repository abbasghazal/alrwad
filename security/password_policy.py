from fastapi import HTTPException


def validate_password_strength(password: str) -> None:
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="كلمة المرور يجب أن تكون 8 أحرف على الأقل")
    if not any(ch.islower() for ch in password):
        raise HTTPException(status_code=400, detail="كلمة المرور يجب أن تحتوي على حرف صغير")
    if not any(ch.isupper() for ch in password):
        raise HTTPException(status_code=400, detail="كلمة المرور يجب أن تحتوي على حرف كبير")
    if not any(ch.isdigit() for ch in password):
        raise HTTPException(status_code=400, detail="كلمة المرور يجب أن تحتوي على رقم")
