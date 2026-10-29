"""One spelling for every address the importer handles. The same page reaches us as
`https://infobeans.ai/agentforce` from one source and `https://www.infobeans.ai/agentforce/` from
another; without a single form they look like different pages, and a page that "disappears" from
the list is really just spelled differently."""

from urllib.parse import urlparse, urlunparse


def canonical_url(url: str) -> str:
    """Lower-case host without `www.`, no fragment or query, and no trailing slash (the site root
    keeps its single slash)."""
    parsed = urlparse(url.strip())
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.rstrip("/")
    scheme = parsed.scheme.lower() or "https"
    return urlunparse((scheme, host, path or "/", "", "", ""))
