"""Reads the offerings out of InfoBeans' own website menu, as an independent list to check the
catalogue against. If the company puts something in its menu under Disciplines or Innovation, it
should be in the catalogue; anything that is not is shown to a person as a possible gap."""

import re
from dataclasses import dataclass
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from app.modules.offerings.retry import with_retries
from app.modules.offerings.urls import canonical_url

# Links in the menu that are promotions or actions, not pages about an offering.
_NOT_AN_OFFERING_LABEL = re.compile(r"^(view|read|play|watch|ask|download|get|book)\b", re.I)


@dataclass(frozen=True)
class MenuItem:
    group: str
    label: str
    url: str


def parse_menu(html: str, base_url: str, groups: list[str]) -> list[MenuItem]:
    """The links under the named top-level menu headings. A heading is a link that goes nowhere
    ("#"); the links after it, up to the next heading, belong to it."""
    soup = BeautifulSoup(html, "lxml")
    nav = soup.find("nav", class_="nav-menu") or soup.find("nav")
    if nav is None:
        return []
    wanted = {g.lower() for g in groups}
    group: str | None = None
    items: list[MenuItem] = []
    seen: set[str] = set()
    for anchor in nav.find_all("a", href=True):
        lines = anchor.get_text("\n", strip=True).split("\n")
        label = re.sub(r"\s+", " ", lines[0]).strip() if lines and lines[0] else ""
        href = anchor["href"].strip()
        if href in ("", "#"):
            group = label
            continue
        if group is None or group.lower() not in wanted or not label:
            continue
        if _NOT_AN_OFFERING_LABEL.match(label) or "?" in href:
            continue
        url = canonical_url(urljoin(base_url, href))
        if url in seen:
            continue
        seen.add(url)
        items.append(MenuItem(group=group, label=label, url=url))
    return items


async def read_menu(url: str, groups: list[str], user_agent: str) -> list[MenuItem]:
    """Raises `httpx.HTTPError` when the home page cannot be read."""
    async def fetch() -> httpx.Response:
        async with httpx.AsyncClient(
            headers={"User-Agent": user_agent}, timeout=20.0, follow_redirects=True
        ) as client:
            return await client.get(url)

    resp = await with_retries(fetch, "reading the website menu")
    resp.raise_for_status()
    return parse_menu(resp.text, str(resp.url), groups)
