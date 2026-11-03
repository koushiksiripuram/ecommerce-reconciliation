"""Role names and helpers.

Roles are stored in the ``roles`` table and seeded by the initial migration.
This module is the single source of truth for the role names the application
code refers to, so a typo cannot silently grant or deny access.
"""

from enum import Enum


class RoleName(str, Enum):
    """Roles recognised by the platform."""

    FINANCE_EXECUTIVE = "finance_executive"
    CO_FOUNDER = "co_founder"


def role_names() -> list[str]:
    """Return every known role name, for validation messages."""
    return [role.value for role in RoleName]
