"""Names the work behind every model call made while an HTTP request is being served.

Jobs already name their calls (the worker sets the task from the job type). Calls made straight
from a route used to land under "unspecified", which made per-task cost impossible to read. This is
registered once for the whole app, so a new route is tagged without anyone remembering to do it."""

from collections.abc import AsyncIterator

from fastapi import Request

from app.modules.usage.context import usage_scope


async def tag_usage_with_route(request: Request) -> AsyncIterator[None]:
    route = request.scope.get("route")
    name = getattr(route, "name", None) or request.url.path
    with usage_scope(task=f"api:{name}"[:60]):  # the task column holds 60 characters
        yield
