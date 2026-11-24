"""Who may do what: one table, read by the API (`require(...)`) and sent to the browser so it hides
what a person's role cannot use.

Agreed on 2026-11-24 (Phase 9). Most rows are open to every role for now on purpose; they are listed
so that narrowing one later is a change to this table only, not to routes or screens."""

from enum import StrEnum

from app.modules.auth.models import USER_ROLE_ADMIN, USER_ROLE_MANAGER, USER_ROLE_REP


class Action(StrEnum):
    # The Users page: invite, change roles, disable, handle access requests.
    USERS_MANAGE = "users.manage"
    # Making someone an admin, or changing or disabling an admin.
    USERS_GRANT_ADMIN = "users.grant_admin"
    # What the AI and search calls cost (`/usage/summary`, the cost card on the dashboard). The
    # dashboard itself is everyone's home page and stays open.
    USAGE_VIEW = "usage.view"
    # Our offerings: products, buyer profiles, the website sync, coverage, proposals.
    OFFERINGS_MANAGE = "offerings.manage"
    ROLE_CATEGORIES_MANAGE = "role_categories.manage"
    # Documents: upload, new version, rename, offerings, read or summarise again, hide cards.
    DOCUMENTS_MANAGE = "documents.manage"
    DOCUMENTS_DELETE = "documents.delete"
    # Work on many companies at once that spends credits: scrape all, verify all, bulk confirm,
    # qualify a whole run.
    BULK_JOBS = "bulk.jobs"
    # Mark many companies "not a fit" at once.
    BULK_DISMISS = "bulk.dismiss"


_EVERYONE = (USER_ROLE_ADMIN, USER_ROLE_MANAGER, USER_ROLE_REP)
_LEADS = (USER_ROLE_ADMIN, USER_ROLE_MANAGER)

PERMISSIONS: dict[Action, tuple[str, ...]] = {
    Action.USERS_MANAGE: _LEADS,
    Action.USERS_GRANT_ADMIN: (USER_ROLE_ADMIN,),
    Action.USAGE_VIEW: _LEADS,
    Action.OFFERINGS_MANAGE: _EVERYONE,
    Action.ROLE_CATEGORIES_MANAGE: _EVERYONE,
    Action.DOCUMENTS_MANAGE: _EVERYONE,
    Action.DOCUMENTS_DELETE: _EVERYONE,
    Action.BULK_JOBS: _EVERYONE,
    Action.BULK_DISMISS: _EVERYONE,
}


def allowed(role: str, action: Action) -> bool:
    return role in PERMISSIONS.get(action, ())


def actions_for(role: str) -> list[str]:
    """Every action this role may take, for the browser."""
    return sorted(action.value for action, roles in PERMISSIONS.items() if role in roles)
