from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from .config import config


# A 4-6 digit PIN has few combinations whatever the cost, and every manager approval checks it against each
# manager, so PINs use a cheaper hash than passwords: approvals stay quick on a small shop PC.
PIN_ROUNDS = 10


def hash_secret(secret: str, rounds: int = 12) -> str:
    return bcrypt.hashpw(secret.encode(), bcrypt.gensalt(rounds)).decode()


def hash_pin(pin: str) -> str:
    return hash_secret(pin, PIN_ROUNDS)


def pin_needs_rehash(hashed: str) -> bool:
    """PINs saved before PIN_ROUNDS existed use the password cost; they are re-saved when next used."""
    try:
        return int(hashed.split("$")[2]) != PIN_ROUNDS
    except (IndexError, ValueError):
        return False


def verify_secret(secret: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(secret.encode(), hashed.encode())
    except ValueError:
        return False


def create_token(user_id: int, role: str) -> str:
    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=config.token_minutes),
    }
    return jwt.encode(payload, config.jwt_secret, algorithm=config.jwt_algorithm)


def decode_token(token: str) -> dict:
    return jwt.decode(token, config.jwt_secret, algorithms=[config.jwt_algorithm])
