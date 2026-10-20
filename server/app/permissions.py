"""What each role may do. The admin can change the manager and cashier columns in the web app (Users page);
the choice is kept in the settings table. The admin role always has everything, so nobody gets locked out.

The defaults are exactly what the roles could do before permissions were editable."""

import json

from sqlalchemy.orm import Session

from .models import ROLE_ADMIN, ROLE_CASHIER, ROLE_MANAGER, Setting, User

# key -> what it allows (shown in the web app)
PERMISSIONS: dict[str, str] = {
    "reports": "Dashboard, reports and every shift",
    "all_sales": "See the sales and shifts of every cashier",
    "approve": "Approve discounts, voids and refunds (their PIN works as the manager PIN)",
    "products": "Add and edit products, categories and barcodes; import / export",
    "inventory": "Receive stock, write off, stock counts and stock history",
    "suppliers": "Suppliers",
}

EDITABLE_ROLES = (ROLE_MANAGER, ROLE_CASHIER)

DEFAULTS: dict[str, set[str]] = {
    ROLE_MANAGER: set(PERMISSIONS),
    ROLE_CASHIER: set(),
}

SETTING_KEY = "role_permissions"


def load(db: Session) -> dict[str, set[str]]:
    """Permissions of every role (admin included)."""
    roles = {role: set(perms) for role, perms in DEFAULTS.items()}
    row = db.get(Setting, SETTING_KEY)
    if row is not None:
        try:
            saved = json.loads(row.value)
        except ValueError:
            saved = {}
        for role in EDITABLE_ROLES:
            if isinstance(saved.get(role), list):
                roles[role] = {p for p in saved[role] if p in PERMISSIONS}
    roles[ROLE_ADMIN] = set(PERMISSIONS)
    return roles


def save(db: Session, roles: dict[str, list[str]]) -> None:
    value = json.dumps({role: sorted(p for p in set(roles.get(role, [])) if p in PERMISSIONS) for role in EDITABLE_ROLES})
    row = db.get(Setting, SETTING_KEY)
    if row is None:
        db.add(Setting(key=SETTING_KEY, value=value))
    else:
        row.value = value


def of(db: Session, user: User) -> set[str]:
    return load(db).get(user.role, set())


def has(db: Session, user: User, *perms: str) -> bool:
    """True when the user has at least one of `perms`."""
    return bool(of(db, user) & set(perms))


def roles_with(db: Session, perm: str) -> list[str]:
    return [role for role, perms in load(db).items() if perm in perms]
