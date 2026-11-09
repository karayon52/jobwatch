import hashlib
from dataclasses import dataclass

import httpx


class ConnectorError(Exception):
    """A readable problem fetching a job source (shown to the user)."""


@dataclass(frozen=True)
class JobData:
    external_id: str
    title: str
    url: str
    location: str = ""
    department: str = ""
    content_hash: str = ""  # changes when the posting is edited


def digest(*parts) -> str:
    return hashlib.sha1("\x1f".join(str(p or "") for p in parts).encode()).hexdigest()


def get(client: httpx.Client, url: str, **kw) -> httpx.Response:
    try:
        r = client.get(url, **kw)
    except httpx.HTTPError as e:
        raise ConnectorError(f"Could not reach the site ({e.__class__.__name__}).") from e
    if r.status_code == 404:
        raise ConnectorError("Job board not found (404). Check the company link.")
    if r.status_code >= 400:
        raise ConnectorError(f"The site returned HTTP {r.status_code}.")
    return r


def get_json(client: httpx.Client, url: str, **kw):
    r = get(client, url, **kw)
    try:
        return r.json()
    except ValueError:
        raise ConnectorError("The site returned data in an unexpected format.") from None
