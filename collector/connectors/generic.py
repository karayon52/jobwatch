"""Fallbacks for companies without a supported ATS: RSS/Atom feeds and best-effort HTML pages."""
import re
from html.parser import HTMLParser
from urllib.parse import urldefrag, urljoin

import httpx
from defusedxml import ElementTree as ET

from .base import ConnectorError, JobData, digest, get


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def rss(client: httpx.Client, url: str) -> list[JobData]:
    r = get(client, url)
    try:
        root = ET.fromstring(r.content)
    except Exception:
        raise ConnectorError("That link is not a valid RSS/Atom feed.") from None
    out = []
    for item in root.iter():
        if _local(item.tag) not in ("item", "entry"):
            continue
        f = {_local(c.tag): c for c in item}
        title = (f["title"].text or "").strip() if "title" in f else ""
        link = ""
        if "link" in f:
            link = f["link"].attrib.get("href") or (f["link"].text or "").strip()
        ident = ((f["guid"].text if "guid" in f else None) or (f["id"].text if "id" in f else None) or link or title).strip()
        desc = (f["description"].text if "description" in f else None) or (f["summary"].text if "summary" in f else "")
        out.append(JobData(ident, title, link, "", "", digest(title, desc)))
    if not out:
        raise ConnectorError("The feed has no entries.")
    return out


_HINT = re.compile(r"(job|career|position|opening|vacanc|role|requisition|apply)", re.I)
_SKIP = re.compile(r"^(mailto:|tel:|javascript:|#)", re.I)


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            self.links.append((self._href, " ".join("".join(self._text).split())))
            self._href = None


def html_page(client: httpx.Client, url: str) -> list[JobData]:
    """Best effort: treats job-looking links on a static page as postings.
    Pages rendered by JavaScript are not supported."""
    r = get(client, url)
    parser = _Links()
    parser.feed(r.text)
    base, _ = urldefrag(url)
    out, seen = [], set()
    for href, text in parser.links:
        if not href or _SKIP.match(href) or not (4 <= len(text) <= 140):
            continue
        full, _ = urldefrag(urljoin(url, href))
        if full == base or full in seen or not _HINT.search(full):
            continue
        seen.add(full)
        out.append(JobData(full, text, full, "", "", digest(text)))
    if not out:
        raise ConnectorError("No job links found. This page may need JavaScript, so try the company's ATS link instead.")
    return out
