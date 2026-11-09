import re
from urllib.parse import parse_qs, urlparse

import httpx

from . import ats, generic
from .base import ConnectorError, JobData

FETCHERS = {
    "greenhouse": ats.greenhouse,
    "lever": ats.lever,
    "ashby": ats.ashby,
    "workable": ats.workable,
    "smartrecruiters": ats.smartrecruiters,
    "rss": generic.rss,
    "html": generic.html_page,
}

_SHORTHAND = re.compile(r"^(greenhouse|lever|ashby|workable|smartrecruiters):([\w.\-]+)$", re.I)
_SLUG = re.compile(r"^[\w.\-]+$")


def fetch_jobs(source: str, slug: str, client: httpx.Client) -> list[JobData]:
    fn = FETCHERS.get(source)
    if not fn:
        raise ConnectorError(f"Unsupported job source: {source}")
    return fn(client, slug)


def detect(raw: str) -> tuple[str, str, str]:
    """Turn what the user pasted into (source, slug, canonical_url)."""
    raw = raw.strip()
    m = _SHORTHAND.match(raw)
    if m:
        source, slug = m.group(1).lower(), m.group(2)
        return source, slug, raw
    u = urlparse(raw if "://" in raw else "https://" + raw)
    host = (u.hostname or "").lower()
    parts = [p for p in u.path.split("/") if p]
    if not host or "." not in host:
        raise ConnectorError("Enter a careers page link, like https://boards.greenhouse.io/acme")

    def need(slug: str | None) -> str:
        if not slug or not _SLUG.match(slug):
            raise ConnectorError("Could not find the company name in that link.")
        return slug

    canon = u.geturl()
    if host.endswith("greenhouse.io"):
        slug = parse_qs(u.query).get("for", [None])[0] or (parts[2] if parts[:2] == ["v1", "boards"] and len(parts) > 2 else (parts[0] if parts else None))
        return "greenhouse", need(slug), canon
    if host.endswith("lever.co"):
        return "lever", need(parts[0] if parts else None), canon
    if host.endswith("ashbyhq.com"):
        return "ashby", need(parts[0] if parts else None), canon
    if host == "apply.workable.com":
        return "workable", need(parts[0] if parts else None), canon
    if host.endswith("smartrecruiters.com"):
        return "smartrecruiters", need(parts[0] if parts else None), canon
    if re.search(r"(\.xml|\.rss|\.atom)$|/feed/?$|/rss/?$", u.path, re.I):
        return "rss", canon, canon
    if u.scheme not in ("http", "https"):
        raise ConnectorError("Only http(s) links are supported.")
    return "html", canon, canon


def guess_name(source: str, slug: str) -> str:
    if source in ("rss", "html"):
        host = (urlparse(slug).hostname or slug).removeprefix("www.").removeprefix("careers.").removeprefix("jobs.")
        return host.split(".")[0].replace("-", " ").title()
    return slug.replace("-", " ").replace("_", " ").title()
