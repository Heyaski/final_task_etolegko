from __future__ import annotations

import json
import re
import secrets
import string
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.config import settings
from app.keitaro import KeitaroError
from app.models import ActivityLog

_ALIAS = string.ascii_letters + string.digits


def parse_geos(raw: str) -> list[str]:
    parts = [part.strip().upper() for part in re.split(r"[\s,;]+", raw or "") if part.strip()]
    if not parts or any(not re.fullmatch(r"[A-Z]{2}", part) for part in parts):
        raise ValueError("Гео — код страны ISO из двух букв. Несколько стран: MX, AU, RO")
    seen: list[str] = []
    for part in parts:
        if part not in seen:
            seen.append(part)
    return seen


def make_alias(length: int = 6) -> str:
    return "".join(secrets.choice(_ALIAS) for _ in range(length))


def _by_name(items: list[dict], name: str) -> dict | None:
    needle = name.strip().lower()
    for item in items:
        if str(item.get("name", "")).strip().lower() == needle:
            return item
    return None


def _domain(items: list[dict], name: str) -> dict | None:
    needle = name.strip().lower().removeprefix("https://").removeprefix("http://").strip("/")
    for item in items:
        host = str(item.get("name", "")).strip().lower().removeprefix("https://").removeprefix("http://").strip("/")
        if host == needle or host.endswith("." + needle):
            return item
    return None


def offer_name(offer: dict) -> str:
    return str(offer.get("name") or offer.get("id"))


def offer_url(offer: dict) -> str:
    payload = str(offer.get("action_payload") or offer.get("url") or "")
    return payload if payload.startswith("http") else ""


def setup_status(client) -> dict:
    domains = client.list_domains()
    groups = client.list_groups("campaigns")
    sources = client.list_traffic_sources()
    domain = _domain(domains, settings.domain_name)
    group = _by_name(groups, settings.group_name)
    source = _by_name(sources, settings.source_name)
    return {
        "domain": _brief(domain),
        "group": _brief(group),
        "source": _brief(source),
        "domain_name": settings.domain_name,
        "group_name": settings.group_name,
        "source_name": settings.source_name,
    }


def _brief(item: dict | None) -> dict | None:
    if not item:
        return None
    return {"id": item.get("id"), "name": item.get("name")}


def list_campaigns(client, query: str = "") -> list[dict]:
    needle = query.strip().lower()
    rows = []
    for campaign in client.list_campaigns():
        if campaign.get("state") == "deleted":
            continue
        name = str(campaign.get("name") or "")
        cid = str(campaign.get("id") or "")
        if needle and needle not in name.lower() and needle not in cid:
            continue
        rows.append(
            {
                "id": campaign.get("id"),
                "name": name,
                "alias": campaign.get("alias") or "",
                "state": campaign.get("state") or "",
                "group_id": campaign.get("group_id"),
            }
        )
    rows.sort(key=lambda item: int(item["id"] or 0), reverse=True)
    return rows


def search_offers(client, query: str = "", limit: int = 20) -> list[dict]:
    needle = query.strip().lower()
    found = []
    for offer in client.list_offers():
        if offer.get("state") in {"deleted", "archived"}:
            continue
        label = offer_name(offer)
        haystack = f"{offer.get('id')} {label} {offer.get('country') or ''}".lower()
        if needle and needle not in haystack:
            continue
        found.append(
            {
                "id": offer.get("id"),
                "name": label,
                "country": offer.get("country") or "",
                "url": offer_url(offer),
            }
        )
        if len(found) >= limit:
            break
    return found


def create_campaign(db: Session, client, name: str, geos: list[str], offer_id: int) -> dict:
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("Введите название кампании")
    status = setup_status(client)
    missing = [
        label
        for label, key in (
            (f"домен {settings.domain_name}", "domain"),
            (f"группа {settings.group_name}", "group"),
            (f"источник {settings.source_name}", "source"),
        )
        if not status[key]
    ]
    if missing:
        raise ValueError("В Keitaro не найдено: " + ", ".join(missing))
    offer = client.get_offer(int(offer_id))

    campaign = None
    last_error: KeitaroError | None = None
    for _ in range(3):
        payload = {
            "name": clean_name,
            "alias": make_alias(),
            "type": "position",
            "state": "active",
            "cost_type": "CPC",
            "cost_value": 0,
            "cost_currency": "USD",
            "cost_auto": True,
            "domain_id": status["domain"]["id"],
            "group_id": status["group"]["id"],
            "traffic_source_id": status["source"]["id"],
        }
        try:
            campaign = client.create_campaign(payload)
            break
        except KeitaroError as exc:
            last_error = exc
            if "alias" not in exc.message.lower():
                raise
    if campaign is None:
        raise last_error or KeitaroError(400, "Не удалось создать кампанию")

    campaign_id = int(campaign["id"])
    try:
        flow_geo = client.create_stream(
            {
                "campaign_id": campaign_id,
                "name": "Flow 1",
                "type": "regular",
                "schema": "redirect",
                "action_type": "http",
                "action_payload": "https://google.com",
                "position": 1,
                "weight": 100,
                "state": "active",
                "collect_clicks": True,
                "filter_or": False,
                "filters": [{"name": "country", "mode": "accept", "payload": geos}],
                "triggers": [],
                "landings": [],
                "offers": [],
            }
        )
        flow_offer = client.create_stream(
            {
                "campaign_id": campaign_id,
                "name": "Flow 2",
                "type": "regular",
                "schema": "landings",
                "action_type": "http",
                "action_payload": "",
                "position": 2,
                "weight": 100,
                "state": "active",
                "collect_clicks": True,
                "filter_or": False,
                "filters": [],
                "triggers": [],
                "landings": [],
                "offers": [{"offer_id": int(offer_id), "share": 100, "state": "active"}],
            }
        )
    except Exception:
        try:
            client.delete_campaign(campaign_id)
        except Exception:
            pass
        raise

    _log(db, "campaign_created", campaign_id, {"name": clean_name, "geos": geos, "offer_id": int(offer_id)})
    return {
        "id": campaign_id,
        "name": campaign.get("name") or clean_name,
        "alias": campaign.get("alias"),
        "url": campaign_url(campaign, getattr(client, "base_url", None)),
        "admin_url": admin_campaign_url(campaign_id, getattr(client, "base_url", None)),
        "geos": geos,
        "offer": {"id": int(offer_id), "name": offer_name(offer)},
        "domain": status["domain"],
        "group": status["group"],
        "source": status["source"],
        "streams": [
            {"id": flow_geo.get("id"), "name": "Flow 1", "target": "https://google.com"},
            {"id": flow_offer.get("id"), "name": "Flow 2", "target": offer_name(offer)},
        ],
    }


def campaign_url(campaign: dict, base_url: str | None = None) -> str:
    alias = str(campaign.get("alias") or "").strip().strip("/")
    if not alias:
        return ""
    return f"{panel_origin(base_url)}/{alias}"


def panel_origin(base_url: str | None = None) -> str:
    root = (base_url or settings.keitaro_base_url).strip().rstrip("/")
    for suffix in ("/admin_api/v1", "/admin_api", "/admin"):
        if root.endswith(suffix):
            root = root[: -len(suffix)]
            break
    return root.rstrip("/")


def admin_campaign_url(campaign_id: int, base_url: str | None = None) -> str:
    return f"{panel_origin(base_url)}/admin/#!/campaign/{campaign_id}/main"


def campaign_detail(client, campaign_id: int) -> dict:
    campaign = client.get_campaign(int(campaign_id))
    offers = {int(item["id"]): item for item in client.list_offers() if item.get("id") is not None}
    streams = []
    for stream in sorted(client.list_streams(int(campaign_id)), key=lambda item: int(item.get("position") or 0)):
        rows = []
        for index, binding in enumerate(stream.get("offers") or []):
            offer_id = int(binding.get("offer_id"))
            offer = offers.get(offer_id, {})
            rows.append(
                {
                    "offer_id": offer_id,
                    "name": offer_name(offer) if offer else f"Offer {offer_id}",
                    "share": int(binding.get("share") or 0),
                    "removed": False,
                    "url": offer_url(offer),
                    "binding_id": binding.get("id"),
                    "_order": index,
                }
            )
        streams.append(
            {
                "id": stream.get("id"),
                "name": stream.get("name") or f"Flow {stream.get('id')}",
                "position": stream.get("position"),
                "schema": stream.get("schema") or "",
                "action_type": stream.get("action_type") or "",
                "action_payload": stream.get("action_payload") or "",
                "filters": _filter_labels(stream.get("filters") or []),
                "offers": rows,
            }
        )
    return {
        "id": campaign.get("id"),
        "name": campaign.get("name") or "",
        "alias": campaign.get("alias") or "",
        "state": campaign.get("state") or "",
        "url": campaign_url(campaign, getattr(client, "base_url", None)),
        "admin_url": admin_campaign_url(int(campaign_id), getattr(client, "base_url", None)),
        "streams": streams,
    }


def _filter_labels(filters: list) -> list[str]:
    labels = []
    for item in filters:
        name = item.get("name") or ""
        mode = item.get("mode") or ""
        payload = item.get("payload")
        if isinstance(payload, list):
            value = ", ".join(str(part) for part in payload)
        else:
            value = str(payload or "")
        if name == "country" and mode == "accept":
            labels.append(f"Страны принимать: {value}")
        else:
            labels.append(f"{name} {mode}: {value}".strip())
    return labels


def push_stream_offers(db: Session, client, campaign_id: int, stream_id: int, offers: list[dict]) -> dict:
    streams = client.list_streams(int(campaign_id))
    stream = next((item for item in streams if int(item.get("id")) == int(stream_id)), None)
    if stream is None:
        raise ValueError("Поток не найден в этой кампании")
    payload_offers = []
    for row in offers:
        if row.get("removed"):
            continue
        share = int(row.get("share") or 0)
        if share < 0:
            raise ValueError("Доля не может быть отрицательной")
        item = {"offer_id": int(row["offer_id"]), "share": share, "state": "active"}
        if row.get("binding_id"):
            item["id"] = int(row["binding_id"])
        payload_offers.append(item)
    update = {"offers": payload_offers}
    if payload_offers and stream.get("schema") == "redirect":
        update["schema"] = "landings"
        update["action_type"] = "http"
        update["action_payload"] = ""
    updated = client.update_stream(int(stream_id), update)
    _log(
        db,
        "stream_pushed",
        int(campaign_id),
        {"stream_id": int(stream_id), "offers": payload_offers},
    )
    return {"stream_id": updated.get("id", stream_id), "offers": updated.get("offers") or payload_offers}


def campaign_stats(client, campaign_id: int) -> dict:
    today = datetime.now().date()
    week_start = today - timedelta(days=6)
    report_range = {
        "from": week_start.isoformat(),
        "to": today.isoformat(),
        "timezone": settings.timezone,
    }
    try:
        totals = client.build_report(
            {
                "range": {"interval": "today", "timezone": settings.timezone},
                "metrics": ["clicks", "campaign_unique_clicks", "conversions", "revenue"],
                "grouping": ["stream_id", "offer_id"],
                "filters": [{"name": "campaign_id", "operator": "EQUALS", "expression": int(campaign_id)}],
                "limit": 1000,
                "offset": 0,
            }
        )
        trend = client.build_report(
            {
                "range": report_range,
                "metrics": ["clicks"],
                "grouping": ["day", "offer_id", "stream_id"],
                "filters": [{"name": "campaign_id", "operator": "EQUALS", "expression": int(campaign_id)}],
                "limit": 1000,
                "offset": 0,
            }
        )
    except KeitaroError as exc:
        return {"ok": False, "error": exc.message, "streams": {}, "offers": {}, "days": []}

    days = [(today - timedelta(days=offset)).isoformat() for offset in range(6, -1, -1)]
    stream_clicks: dict[str, int] = {}
    offer_stats: dict[str, dict] = {}
    for row in _rows(totals):
        stream_key = str(_first(row, "stream_id", "stream") or "")
        offer_key = str(_first(row, "offer_id", "offer") or "")
        clicks = int(_first(row, "clicks") or 0)
        if stream_key:
            stream_clicks[stream_key] = stream_clicks.get(stream_key, 0) + clicks
        if offer_key and offer_key != "0":
            bucket = offer_stats.setdefault(
                offer_key,
                {"clicks": 0, "unique": 0, "conversions": 0, "revenue": 0.0, "trend": [0] * len(days)},
            )
            bucket["clicks"] += clicks
            bucket["unique"] += int(_first(row, "campaign_unique_clicks", "unique_clicks") or 0)
            bucket["conversions"] += int(_first(row, "conversions") or 0)
            bucket["revenue"] += float(_first(row, "revenue") or 0)

    day_index = {day: index for index, day in enumerate(days)}
    for row in _rows(trend):
        offer_key = str(_first(row, "offer_id", "offer") or "")
        day = str(_first(row, "day", "date") or "")[:10]
        if offer_key in offer_stats and day in day_index:
            offer_stats[offer_key]["trend"][day_index[day]] += int(_first(row, "clicks") or 0)
    return {"ok": True, "streams": stream_clicks, "offers": offer_stats, "days": days}


def _rows(report: dict) -> list:
    if isinstance(report, dict):
        return report.get("rows") or []
    return []


def _first(row: dict, *keys):
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return None


def recent_activity(db: Session, limit: int = 12) -> list[ActivityLog]:
    return db.query(ActivityLog).order_by(ActivityLog.id.desc()).limit(limit).all()


def _log(db: Session, action: str, campaign_id: int | None, detail: dict) -> None:
    db.add(ActivityLog(action=action, campaign_id=campaign_id, detail=json.dumps(detail, ensure_ascii=False)))
    db.commit()
