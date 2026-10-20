from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Setting

DEFAULTS: dict[str, str] = {
    "store_name": "RATHA MART",
    "store_address": "Phnom Penh, Cambodia",
    "store_phone": "",
    "tax_rate_bp": "1000",  # 10.00% VAT
    "tax_inclusive": "false",
    "exchange_rate": "4100",  # KHR per 1 USD
    "receipt_footer": "Thank you! Please come again.",
    "allow_negative_stock": "true",
    "loyalty_points_per_usd": "1",
    "logo_url": "",  # set by uploading a logo in Settings
}

INT_KEYS = {"tax_rate_bp", "exchange_rate", "loyalty_points_per_usd"}
BOOL_KEYS = {"tax_inclusive", "allow_negative_stock"}


def load(db: Session) -> dict[str, str]:
    values = dict(DEFAULTS)
    values.update({s.key: s.value for s in db.scalars(select(Setting))})
    return values


def get_int(values: dict[str, str], key: str) -> int:
    return int(values[key])


def get_bool(values: dict[str, str], key: str) -> bool:
    return values[key].lower() == "true"


def save(db: Session, changes: dict[str, str]) -> None:
    for key, value in changes.items():
        row = db.get(Setting, key)
        if row is None:
            db.add(Setting(key=key, value=value))
        else:
            row.value = value
