"""Optional push alerts. Enabled only when the matching repository secrets exist."""
import logging
import os

import httpx

log = logging.getLogger("collector.notify")
MAX_LINES = 10


def _compose(company: str, events: list[dict]) -> tuple[str, str]:
    new = sum(1 for e in events if e["kind"] == "new")
    upd = len(events) - new
    parts = ([f"{new} new"] if new else []) + ([f"{upd} updated"] if upd else [])
    title = f"{company}: {', '.join(parts)} job post{'s' if len(events) != 1 else ''}"
    lines = []
    for e in events[:MAX_LINES]:
        loc = f" – {e['location']}" if e["location"] else ""
        tag = " (updated)" if e["kind"] == "updated" else ""
        lines.append(f"• {e['title']}{loc}{tag}\n  {e['url']}")
    if len(events) > MAX_LINES:
        lines.append(f"…and {len(events) - MAX_LINES} more")
    return title, "\n".join(lines)


def push(notifications: list[dict]) -> None:
    if not notifications:
        return
    by_company: dict[str, list[dict]] = {}
    for n in notifications:
        by_company.setdefault(n["company"], []).append(n)
    ntfy = os.getenv("NTFY_TOPIC", "").strip()
    tg_token, tg_chat = os.getenv("TELEGRAM_BOT_TOKEN", "").strip(), os.getenv("TELEGRAM_CHAT_ID", "").strip()
    for company, events in by_company.items():
        title, body = _compose(company, events)
        try:
            if ntfy:
                httpx.post(f"https://ntfy.sh/{ntfy}", content=body.encode(), timeout=15,
                           headers={"Title": title.encode("ascii", "ignore").decode(), "Click": events[0]["url"]})
            if tg_token and tg_chat:
                httpx.post(f"https://api.telegram.org/bot{tg_token}/sendMessage", timeout=15,
                           json={"chat_id": tg_chat, "text": f"{title}\n\n{body}"[:4000], "disable_web_page_preview": True})
        except httpx.HTTPError as e:
            log.warning("Push failed for %s: %s", company, e.__class__.__name__)
