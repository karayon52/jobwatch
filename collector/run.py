"""Collect jobs for every company in companies.yml, diff against saved state, and write the results to data/."""
import hashlib
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import yaml

from . import notify
from .connectors.base import ConnectorError, JobData, digest
from .connectors.registry import detect, fetch_jobs, guess_name

log = logging.getLogger("collector")
ROOT = Path(__file__).resolve().parent.parent
MAX_BASELINE_ANNOUNCE = 50


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def norm(s: str) -> str:
    return re.sub(r"\W+", " ", (s or "").lower()).strip()


def fingerprint(title: str, location: str) -> str:
    return digest(norm(title), norm(location))


def matches(entry: dict, job: dict) -> bool:
    terms = lambda k: [t.strip().lower() for t in entry.get(k, []) if str(t).strip()]  # noqa: E731
    text = f"{job['title']} {job.get('department', '')}".lower()
    loc = (job.get("location") or "").lower()
    inc, exc, locs = terms("include"), terms("exclude"), terms("locations")
    if inc and not any(t in text for t in inc):
        return False
    if exc and any(t in text for t in exc):
        return False
    if locs and not any(t in loc for t in locs):
        return False
    return True


# ---------- config ----------
def company_key(source: str, slug: str) -> str:
    if source in ("rss", "html"):
        return f"{source}-{hashlib.sha1(slug.encode()).hexdigest()[:10]}"
    return f"{source}-{re.sub(r'[^a-z0-9]+', '-', slug.lower()).strip('-')[:40]}"


def _words(v) -> list[str]:
    if isinstance(v, str):
        v = [x for x in v.split(",")]
    return [str(x).strip() for x in (v or []) if str(x).strip()]


def load_config(path: Path) -> tuple[dict, list[dict], list[str]]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    settings = {"keep_notifications": 1500, "repost_window_days": 30, **(raw.get("settings") or {})}
    entries, errors, seen = [], [], set()
    for i, item in enumerate(raw.get("companies") or [], 1):
        item = {"url": item} if isinstance(item, str) else (item or {})
        url = str(item.get("url", "")).strip()
        try:
            source, slug, canon = detect(url)
        except ConnectorError as e:
            errors.append(f"Company #{i} ({url or 'no url'}): {e}")
            continue
        key = company_key(source, slug)
        if key in seen:
            errors.append(f"Company #{i} ({url}) is listed twice.")
            continue
        seen.add(key)
        entries.append({
            "key": key, "source": source, "slug": slug, "url": canon,
            "name": str(item.get("name") or guess_name(source, slug)),
            "include": _words(item.get("include")), "exclude": _words(item.get("exclude")),
            "locations": _words(item.get("locations")),
            "notify_updates": bool(item.get("notify_updates", True)),
            "announce_existing": bool(item.get("announce_existing", False)),
        })
    return settings, entries, errors


# ---------- diffing (pure; operates on a plain dict) ----------
def apply_snapshot(state: dict, jobs: list[JobData], now: datetime, repost_days: int = 30,
                   announce_existing: bool = False) -> list[tuple[str, dict]]:
    """Update `state` in place and return [(kind, job)] events. The first snapshot is a silent baseline."""
    first = not state.get("baselined")
    store = state.setdefault("jobs", {})
    stamp = iso(now)
    cutoff = iso(now - timedelta(days=repost_days))
    ids = {j.external_id for j in jobs}
    events: list[tuple[str, dict]] = []

    # Close vanished jobs first, so a repost under a new ID in the same run is recognised.
    # An empty snapshot is more likely an upstream glitch than every job closing.
    if ids:
        for ext, row in store.items():
            if ext not in ids and not row.get("closed_at"):
                row["closed_at"] = stamp
    closed_fps = {r["fp"] for r in store.values() if r.get("closed_at") and r["closed_at"] >= cutoff}

    done: set[str] = set()
    for jd in jobs:
        if jd.external_id in done:
            continue
        done.add(jd.external_id)
        row = store.get(jd.external_id)
        if row is None:
            fp = fingerprint(jd.title, jd.location)
            row = {"title": jd.title, "location": jd.location, "department": jd.department, "url": jd.url,
                   "hash": jd.content_hash, "fp": fp, "first_seen": stamp, "closed_at": None}
            store[jd.external_id] = row
            if first:
                if announce_existing:
                    events.append(("new", {**row, "id": jd.external_id}))
            elif fp not in closed_fps:
                events.append(("new", {**row, "id": jd.external_id}))
        else:
            row["closed_at"] = None
            if row["hash"] != jd.content_hash:
                row.update(title=jd.title, location=jd.location, department=jd.department, url=jd.url,
                           hash=jd.content_hash, fp=fingerprint(jd.title, jd.location))
                if not first:
                    events.append(("updated", {**row, "id": jd.external_id}))

    for ext in [e for e, r in store.items() if r.get("closed_at") and r["closed_at"] < cutoff]:
        del store[ext]
    state["baselined"] = True
    return events


# ---------- storage ----------
def _write(path: Path, obj, compact=False) -> bool:
    text = json.dumps(obj, sort_keys=True, ensure_ascii=False,
                      **({"separators": (",", ":")} if compact else {"indent": 1})) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.write_text(text, encoding="utf-8")
    return True


def _read(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def make_client() -> httpx.Client:
    return httpx.Client(timeout=20, follow_redirects=True, transport=httpx.HTTPTransport(retries=2),
                        headers={"User-Agent": "JobWatch/1.0 (+https://github.com)", "Accept": "application/json, text/html;q=0.9, */*;q=0.5"})


def main(config_path: Path = ROOT / "companies.yml", data_dir: Path = ROOT / "data",
         fetch=fetch_jobs, client=None, now: datetime | None = None, send_push: bool = True) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    settings, entries, config_errors = load_config(config_path)
    (data_dir / "companies").mkdir(parents=True, exist_ok=True)
    client = client or make_client()

    def work(entry):
        try:
            return fetch(entry["source"], entry["slug"], client), None
        except ConnectorError as e:
            return None, str(e)
        except Exception:
            log.exception("Unexpected error for %s", entry["name"])
            return None, "Unexpected error while checking this company."

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(work, entries))

    old_status = _read(data_dir / "status.json", {}).get("companies", {})
    notifications = _read(data_dir / "notifications.json", [])
    known = {n["id"] for n in notifications}
    fresh: list[dict] = []
    status: dict = {}

    for entry, (jobs, err) in zip(entries, results):
        path = data_dir / "companies" / f"{entry['key']}.json"
        state = _read(path, {"baselined": False, "jobs": {}})
        prev = old_status.get(entry["key"], {})
        if err:
            log.warning("%s: %s", entry["name"], err)
            status[entry["key"]] = {"name": entry["name"], "source": entry["source"], "url": entry["url"], "ok": False,
                                    "error": err, "failing_since": prev.get("failing_since") or iso(now),
                                    "open": sum(1 for j in state["jobs"].values() if not j.get("closed_at"))}
            continue
        events = apply_snapshot(state, jobs, now, settings["repost_window_days"], entry["announce_existing"])
        added = 0
        for kind, job in events:
            if (kind == "updated" and not entry["notify_updates"]) or not matches(entry, job):
                continue
            nid = digest(entry["key"], job["id"], kind, job["hash"])[:16]
            if nid in known:
                continue
            if state_is_baseline_announce(kind, events) and added >= MAX_BASELINE_ANNOUNCE:
                break
            known.add(nid)
            added += 1
            fresh.append({"id": nid, "ts": iso(now), "kind": kind, "company": entry["name"], "company_key": entry["key"],
                          "title": job["title"], "location": job["location"], "department": job["department"], "url": job["url"]})
        _write(path, state, compact=True)
        status[entry["key"]] = {"name": entry["name"], "source": entry["source"], "url": entry["url"], "ok": True,
                                "error": None, "failing_since": None,
                                "open": sum(1 for j in state["jobs"].values() if not j.get("closed_at"))}

    # Remove data for companies no longer in companies.yml.
    live = {e["key"] for e in entries}
    for f in (data_dir / "companies").glob("*.json"):
        if f.stem not in live:
            f.unlink()

    notifications = (fresh + notifications)[: int(settings["keep_notifications"])]
    _write(data_dir / "notifications.json", notifications)
    _write(data_dir / "status.json", {"companies": status, "config_errors": config_errors})
    log.info("Checked %d companies, %d new alerts", len(entries), len(fresh))
    if send_push:
        notify.push(fresh)
    return fresh


def state_is_baseline_announce(kind: str, events) -> bool:
    return len(events) > MAX_BASELINE_ANNOUNCE and kind == "new"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    main()
