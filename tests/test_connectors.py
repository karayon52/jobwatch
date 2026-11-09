import httpx
import pytest

from collector.connectors import ats, generic
from collector.connectors.base import ConnectorError
from collector.connectors.registry import detect


def client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.mark.parametrize("raw,expected", [
    ("https://boards.greenhouse.io/acme", ("greenhouse", "acme")),
    ("https://job-boards.greenhouse.io/acme/jobs/123", ("greenhouse", "acme")),
    ("https://jobs.lever.co/netflix", ("lever", "netflix")),
    ("jobs.ashbyhq.com/ramp", ("ashby", "ramp")),
    ("https://apply.workable.com/foo/", ("workable", "foo")),
    ("lever:stripe", ("lever", "stripe")),
])
def test_detect_ats(raw, expected):
    assert detect(raw)[:2] == expected


def test_detect_rss_and_html_and_garbage():
    assert detect("https://example.com/jobs.xml")[0] == "rss"
    assert detect("https://example.com/careers")[0] == "html"
    with pytest.raises(ConnectorError):
        detect("not a url")


def test_greenhouse_parse_and_404():
    def ok(req):
        return httpx.Response(200, json={"jobs": [{"id": 7, "title": "SRE", "absolute_url": "https://g/7",
                                                   "location": {"name": "Remote"}, "updated_at": "2026-01-01"}]})
    jobs = ats.greenhouse(client(ok), "acme")
    assert jobs[0].external_id == "7" and jobs[0].location == "Remote"
    with pytest.raises(ConnectorError, match="not found"):
        ats.greenhouse(client(lambda r: httpx.Response(404)), "nope")


def test_lever_falls_back_to_eu():
    def h(req):
        if req.url.host == "api.lever.co":
            return httpx.Response(404)
        return httpx.Response(200, json=[{"id": "a", "text": "Dev", "hostedUrl": "u", "categories": {"location": "Paris"}}])
    assert ats.lever(client(h), "eu-co")[0].location == "Paris"


def test_rss_and_html():
    feed = b"<rss><channel><item><title>Dev</title><link>https://e/1</link><guid>1</guid></item></channel></rss>"
    assert generic.rss(client(lambda r: httpx.Response(200, content=feed)), "https://e/feed")[0].title == "Dev"
    page = '<a href="/jobs/42">Senior Engineer</a><a href="/about">About us</a><a href="/careers/9">Designer</a>'
    jobs = generic.html_page(client(lambda r: httpx.Response(200, text=page)), "https://e.com/careers")
    assert {j.title for j in jobs} == {"Senior Engineer", "Designer"}
