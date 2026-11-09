import json
from datetime import datetime, timedelta, timezone

import pytest

from collector import run
from collector.connectors.base import ConnectorError, JobData

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def jd(i, title="Engineer", loc="Berlin", h=None):
    return JobData(str(i), title, f"https://x.test/{i}", loc, "", h or f"h-{title}-{loc}")


def test_baseline_then_new_updated():
    st = {}
    assert run.apply_snapshot(st, [jd(1), jd(2)], NOW) == []
    ev = run.apply_snapshot(st, [jd(1), jd(2, h="edited"), jd(3, "Designer")], NOW)
    assert sorted(k for k, _ in ev) == ["new", "updated"]


def test_announce_existing_on_first_run():
    assert len(run.apply_snapshot({}, [jd(1), jd(2, "Other")], NOW, announce_existing=True)) == 2


def test_repost_same_run_and_empty_snapshot_guard():
    st = {}
    run.apply_snapshot(st, [jd(1), jd(2, "Chef", "Paris")], NOW)
    # job 1 vanishes, same title+location reappears under a new id in the SAME snapshot => repost, no alert
    assert run.apply_snapshot(st, [jd(99), jd(2, "Chef", "Paris")], NOW + timedelta(minutes=5)) == []
    assert st["jobs"]["1"]["closed_at"]
    # empty snapshot closes nothing
    run.apply_snapshot(st, [], NOW + timedelta(minutes=10))
    assert not st["jobs"]["99"]["closed_at"]


def test_old_closed_jobs_are_pruned():
    st = {}
    run.apply_snapshot(st, [jd(1), jd(2, "B")], NOW)
    run.apply_snapshot(st, [jd(2, "B")], NOW + timedelta(days=1))
    run.apply_snapshot(st, [jd(2, "B")], NOW + timedelta(days=40))
    assert "1" not in st["jobs"]


def test_matching():
    e = {"include": ["engineer"], "exclude": ["intern"], "locations": ["remote"]}
    assert run.matches(e, {"title": "Backend Engineer", "location": "Remote - EU"})
    assert not run.matches(e, {"title": "Engineer Intern", "location": "Remote"})
    assert not run.matches(e, {"title": "Engineer", "location": "Paris"})


def test_config_loading(tmp_path):
    p = tmp_path / "c.yml"
    p.write_text("""
companies:
  - url: https://boards.greenhouse.io/acme
    include: "engineer, data"
  - lever:foo
  - url: not a url
  - url: greenhouse:acme
""")
    _, entries, errors = run.load_config(p)
    assert [e["key"] for e in entries] == ["greenhouse-acme", "lever-foo"]
    assert entries[0]["include"] == ["engineer", "data"]
    assert len(errors) == 2


def test_end_to_end(tmp_path):
    cfg = tmp_path / "companies.yml"
    cfg.write_text("companies:\n  - url: greenhouse:acme\n    include: [engineer]\n  - url: lever:broken\n")
    data = tmp_path / "data"
    snaps = {"acme": [jd(1)], }

    def fetch(source, slug, client):
        if slug == "broken":
            raise ConnectorError("Job board not found (404). Check the company link.")
        return snaps[slug]

    assert run.main(cfg, data, fetch=fetch, now=NOW, send_push=False) == []          # baseline: silent
    snaps["acme"] = [jd(1), jd(2, "Backend Engineer"), jd(3, "Chef")]
    fresh = run.main(cfg, data, fetch=fetch, now=NOW + timedelta(minutes=10), send_push=False)
    assert [n["title"] for n in fresh] == ["Backend Engineer"]                        # Chef filtered out
    assert run.main(cfg, data, fetch=fetch, now=NOW + timedelta(minutes=20), send_push=False) == []   # no duplicates
    inbox = json.loads((data / "notifications.json").read_text())
    assert len(inbox) == 1 and inbox[0]["company"] == "Acme"
    status = json.loads((data / "status.json").read_text())["companies"]
    assert status["greenhouse-acme"]["ok"] and status["greenhouse-acme"]["open"] == 3
    assert not status["lever-broken"]["ok"] and "not found" in status["lever-broken"]["error"]
    # status is stable between runs (so unchanged runs make no git commit)
    before = (data / "status.json").read_text()
    run.main(cfg, data, fetch=fetch, now=NOW + timedelta(hours=3), send_push=False)
    assert (data / "status.json").read_text() == before
