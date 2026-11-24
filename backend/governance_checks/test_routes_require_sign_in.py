"""Phase 9: every API route requires a signed-in person with an active account, except a short
public list, and every permission a route asks for is one the permission table knows.

The check calls every endpoint the app serves (read from its OpenAPI description) without signing in
and expects 401 "sign in" before anything else happens, so a router mounted without the sign-in
check fails here, whatever FastAPI does internally. No key, no network, no database: the refusal
comes before any of them is touched."""

import re
import uuid
from typing import Any

from fastapi.testclient import TestClient

from app.main import app
from app.modules.auth.deps import _Require
from app.modules.auth.permissions import PERMISSIONS, Action

# Open without signing in, and why.
PUBLIC = {"/api/v1/health": "the uptime check"}
# Need a verified Google account (401 without one) but no access yet: who am I, ask for access.
IDENTITY_ONLY = {"/api/v1/auth/me", "/api/v1/auth/access-requests"}

_PARAM = re.compile(r"\{[^}]+\}")


def _operations() -> list[tuple[str, str]]:
    spec = app.openapi()
    return sorted(
        (method.upper(), path)
        for path, item in spec["paths"].items()
        for method in item
        if method in {"get", "post", "put", "patch", "delete"}
    )


def test_every_route_refuses_a_request_without_sign_in() -> None:
    client = TestClient(app)
    some_id = str(uuid.uuid4())
    open_routes = []
    for method, path in _operations():
        if path in PUBLIC:
            continue
        response = client.request(method, _PARAM.sub(some_id, path), json={})
        detail = response.json().get("detail") if response.content else None
        code = detail.get("code") if isinstance(detail, dict) else None
        if not (response.status_code == 401 and code == "signed_out"):
            open_routes.append(f"{method} {path} -> {response.status_code}")
    assert not open_routes, (
        f"{open_routes} did not ask for sign-in. Mount the router with "
        "dependencies=[Depends(signed_in)] in app/main.py, or list it here with a reason."
    )


def test_the_lists_only_name_routes_that_exist() -> None:
    paths = {path for _, path in _operations()}
    assert set(PUBLIC) <= paths and IDENTITY_ONLY <= paths


def _required_actions() -> set[Action]:
    """The actions routes ask for: every `require(...)` the routers hold."""
    found: set[Action] = set()

    def walk(dependant) -> None:  # type: ignore[no-untyped-def]
        for sub in dependant.dependencies:
            if isinstance(sub.call, _Require):
                found.add(sub.call.action)
            walk(sub)

    def routes(container) -> list[Any]:  # type: ignore[no-untyped-def]
        out = []
        for route in getattr(container, "routes", []):
            if hasattr(route, "dependant"):
                out.append(route)
            inner = getattr(route, "original_router", None) or getattr(route, "router", None)
            if inner is not None and inner is not container:
                out.extend(routes(inner))
        return out

    for route in routes(app.router):
        walk(route.dependant)
    return found


def test_every_permission_a_route_asks_for_is_in_the_table() -> None:
    asked = _required_actions()
    assert asked <= set(PERMISSIONS)
    assert set(Action) == set(PERMISSIONS), "every action needs a row in the permission table"
    # The rows that refuse reps today are really attached to routes.
    assert {Action.USERS_MANAGE, Action.USAGE_VIEW} <= asked, asked
