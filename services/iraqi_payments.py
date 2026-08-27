import re
import secrets
from typing import Dict

from fastapi import HTTPException


IRAQI_PHONE_PATTERN = re.compile(r"^\+?9647\d{9}$|^07\d{9}$")

PAYMENT_METHODS: Dict[str, Dict[str, str]] = {
    "zain_cash": {
        "name": "Zain Cash",
        "kind": "mobile_wallet",
        "instructions": "يدفع الطالب من محفظة زين كاش ثم يرسل رقم الهاتف ومرجع العملية.",
    },
    "asia_hawala": {
        "name": "AsiaHawala",
        "kind": "mobile_wallet",
        "instructions": "يدفع الطالب من محفظة آسيا حوالة ثم يرسل رقم الهاتف ومرجع العملية.",
    },
    "fastpay": {
        "name": "FastPay",
        "kind": "mobile_wallet",
        "instructions": "يدفع الطالب عبر FastPay ثم يرسل رقم الهاتف ومرجع العملية.",
    },
    "qi_card": {
        "name": "Qi Card",
        "kind": "card_or_wallet",
        "instructions": "يدفع الطالب عبر قناة Qi المتاحة ثم يرسل رقم الهاتف أو رقم العملية المرجعي.",
    },
    "mastercard": {
        "name": "Mastercard",
        "kind": "card_gateway",
        "instructions": "يستخدم هذا الخيار عند ربط بوابة بطاقات تدعم Mastercard؛ حاليًا يتم تسجيل العملية للمراجعة أو Webhook.",
    },
}


def normalize_iraqi_phone(phone: str) -> str:
    cleaned = phone.strip().replace(" ", "").replace("-", "")
    if cleaned.startswith("00964"):
        cleaned = "+964" + cleaned[5:]
    if not IRAQI_PHONE_PATTERN.match(cleaned):
        raise HTTPException(status_code=400, detail="رقم الهاتف العراقي غير صحيح. استخدم 07XXXXXXXXX أو +9647XXXXXXXXX")
    if cleaned.startswith("07"):
        return "+964" + cleaned[1:]
    return cleaned


def validate_payment_method(method: str) -> Dict[str, str]:
    if method not in PAYMENT_METHODS:
        raise HTTPException(status_code=400, detail="طريقة الدفع غير مدعومة")
    return PAYMENT_METHODS[method]


def generate_payment_reference(method: str) -> str:
    return f"{method.upper()}-{secrets.token_urlsafe(8)}"
