"""Connectors for hosted applicant-tracking systems with public JSON feeds."""
import httpx

from .base import ConnectorError, JobData, digest, get_json


def greenhouse(client: httpx.Client, slug: str) -> list[JobData]:
    data = get_json(client, f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs")
    out = []
    for j in data.get("jobs", []):
        loc = (j.get("location") or {}).get("name", "")
        title = (j.get("title") or "").strip()
        out.append(JobData(str(j["id"]), title, j.get("absolute_url", ""), loc, "",
                           digest(title, loc, j.get("updated_at"))))
    return out


def lever(client: httpx.Client, slug: str) -> list[JobData]:
    data, last = None, None
    for host in ("api.lever.co", "api.eu.lever.co"):
        try:
            data = get_json(client, f"https://{host}/v0/postings/{slug}", params={"mode": "json"})
            break
        except ConnectorError as e:
            last = e
            if "404" not in str(e):
                raise
    if data is None:
        raise last  # type: ignore[misc]
    out = []
    for j in data:
        cat = j.get("categories") or {}
        title = (j.get("text") or "").strip()
        out.append(JobData(j["id"], title, j.get("hostedUrl", ""), cat.get("location") or "",
                           cat.get("team") or cat.get("department") or "",
                           digest(title, cat.get("location"), j.get("descriptionPlain"))))
    return out


def ashby(client: httpx.Client, slug: str) -> list[JobData]:
    data = get_json(client, f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
    out = []
    for j in data.get("jobs", []):
        if j.get("isListed") is False:
            continue
        title = (j.get("title") or "").strip()
        loc = j.get("location") or ""
        out.append(JobData(j["id"], title, j.get("jobUrl", ""), loc, j.get("department") or j.get("team") or "",
                           digest(title, loc, j.get("descriptionHtml") or j.get("descriptionPlain"))))
    return out


def workable(client: httpx.Client, slug: str) -> list[JobData]:
    data = get_json(client, f"https://apply.workable.com/api/v1/widget/accounts/{slug}")
    out = []
    for j in data.get("jobs", []):
        title = (j.get("title") or "").strip()
        loc = ", ".join(x for x in (j.get("city"), j.get("state"), j.get("country")) if x)
        out.append(JobData(j["shortcode"], title, j.get("url", ""), loc, j.get("department") or "",
                           digest(title, loc, j.get("department"))))
    return out


def smartrecruiters(client: httpx.Client, slug: str) -> list[JobData]:
    out, offset = [], 0
    while offset < 1000:
        data = get_json(client, f"https://api.smartrecruiters.com/v1/companies/{slug}/postings",
                        params={"limit": 100, "offset": offset})
        items = data.get("content", [])
        for j in items:
            loc_d = j.get("location") or {}
            loc = ", ".join(x for x in (loc_d.get("city"), loc_d.get("country", "").upper()) if x)
            title = (j.get("name") or "").strip()
            out.append(JobData(str(j["id"]), title, f"https://jobs.smartrecruiters.com/{slug}/{j['id']}",
                               loc, (j.get("department") or {}).get("label", ""),
                               digest(title, loc, j.get("releasedDate"))))
        offset += 100
        if not items or offset >= data.get("totalFound", 0):
            break
    return out
