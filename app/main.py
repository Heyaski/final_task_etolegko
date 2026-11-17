from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import ROOT, settings
from app.database import get_db
from app.fake import FakeKeitaro
from app.keitaro import KeitaroClient, KeitaroError
from app.models import AppSetting, utcnow
from app.service import (
    campaign_detail,
    campaign_stats,
    create_campaign,
    list_campaigns,
    parse_geos,
    push_stream_offers,
    recent_activity,
    search_offers,
    setup_status,
)
from app.share import active_sum, apply_share_op

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def run_migrations() -> None:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", settings.database_url)
    command.upgrade(cfg, "head")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    run_migrations()
    yield


app = FastAPI(title="Keitaro wrapper", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")


def credentials(db: Session) -> tuple[str, str]:
    row = db.get(AppSetting, 1)
    url = (row.keitaro_base_url if row and row.keitaro_base_url else settings.keitaro_base_url).rstrip("/")
    key = row.keitaro_api_key if row and row.keitaro_api_key else settings.keitaro_api_key
    return url, key.strip()


def client_for(db: Session):
    url, key = credentials(db)
    mock = settings.keitaro_mock or not key
    if mock:
        return _FAKE, True, url
    return KeitaroClient(url, key), False, url


def page(request: Request, template: str, db: Session, **extra):
    _client, mock, url = client_for(db)
    context = {"mock": mock, "keitaro_url": url, "page": ""}
    context.update(extra)
    return TEMPLATES.TemplateResponse(request, template, context)


def api_error(exc: Exception) -> HTTPException:
    if isinstance(exc, KeitaroError):
        return HTTPException(status_code=502, detail=exc.message)
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    raise exc


class CampaignIn(BaseModel):
    name: str
    geo: str
    offer_id: int


class ShareIn(BaseModel):
    op: str
    rows: list[dict] = Field(default_factory=list)
    offer_id: int | None = None
    delta: int = 0
    offer: dict | None = None


class PushIn(BaseModel):
    offers: list[dict]


_FAKE = FakeKeitaro()


@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    return page(request, "create.html", db, page="create")


@app.get("/campaigns", response_class=HTMLResponse)
def campaigns_page(request: Request, q: str = "", db: Session = Depends(get_db)):
    client, mock, url = client_for(db)
    try:
        rows = list_campaigns(client, q)
        error = ""
    except KeitaroError as exc:
        rows = []
        error = exc.message
    return TEMPLATES.TemplateResponse(
        request,
        "campaigns.html",
        {
            "mock": mock,
            "keitaro_url": url,
            "page": "campaigns",
            "campaigns": rows,
            "query": q,
            "error": error,
            "activity": recent_activity(db),
        },
    )


@app.get("/campaigns/{campaign_id}", response_class=HTMLResponse)
def editor_page(campaign_id: int, request: Request, db: Session = Depends(get_db)):
    client, mock, url = client_for(db)
    try:
        detail = campaign_detail(client, campaign_id)
    except KeitaroError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    return TEMPLATES.TemplateResponse(
        request,
        "editor.html",
        {
            "mock": mock,
            "keitaro_url": url,
            "page": "editor",
            "campaign": detail,
            "boot": json.dumps(detail, ensure_ascii=False).replace("<", "\\u003c"),
        },
    )


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, db: Session = Depends(get_db)):
    url, key = credentials(db)
    return page(request, "settings.html", db, page="settings", base_url=url, has_key=bool(key), saved="")


@app.post("/settings", response_class=HTMLResponse)
async def settings_save(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    url = str(form.get("keitaro_base_url") or "").strip().rstrip("/")
    key = str(form.get("keitaro_api_key") or "").strip()
    if not url.startswith("http"):
        return page(request, "settings.html", db, page="settings", base_url=url, has_key=bool(key), saved="Адрес должен начинаться с http:// или https://")
    row = db.get(AppSetting, 1)
    if row is None:
        row = AppSetting(id=1, keitaro_base_url=url, keitaro_api_key=key, updated_at=utcnow())
        db.add(row)
    else:
        row.keitaro_base_url = url
        if key:
            row.keitaro_api_key = key
        row.updated_at = utcnow()
    db.commit()
    return page(
        request,
        "settings.html",
        db,
        page="settings",
        base_url=url,
        has_key=bool(row.keitaro_api_key),
        saved="Сохранено. Пустое поле ключа оставляет прежний ключ.",
    )


@app.get("/api/setup")
def api_setup(db: Session = Depends(get_db)):
    client, mock, url = client_for(db)
    try:
        status = setup_status(client)
    except KeitaroError as exc:
        raise api_error(exc) from exc
    status["mock"] = mock
    status["keitaro_url"] = url
    return status


@app.get("/api/offers")
def api_offers(q: str = "", limit: int = 20, db: Session = Depends(get_db)):
    client, _mock, _url = client_for(db)
    try:
        return search_offers(client, q, max(1, min(limit, 100)))
    except KeitaroError as exc:
        raise api_error(exc) from exc


@app.post("/api/campaigns")
def api_create(body: CampaignIn, db: Session = Depends(get_db)):
    client, _mock, _url = client_for(db)
    try:
        geos = parse_geos(body.geo)
        return create_campaign(db, client, body.name, geos, body.offer_id)
    except (KeitaroError, ValueError) as exc:
        raise api_error(exc) from exc


@app.post("/api/shares")
def api_shares(body: ShareIn):
    try:
        rows = apply_share_op(body.rows, body.op, body.offer_id, body.delta, body.offer)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"rows": rows, "sum": active_sum(rows)}


@app.post("/api/campaigns/{campaign_id}/streams/{stream_id}")
def api_push(campaign_id: int, stream_id: int, body: PushIn, db: Session = Depends(get_db)):
    client, _mock, _url = client_for(db)
    try:
        return push_stream_offers(db, client, campaign_id, stream_id, body.offers)
    except (KeitaroError, ValueError) as exc:
        raise api_error(exc) from exc


@app.get("/api/campaigns/{campaign_id}/stats")
def api_stats(campaign_id: int, db: Session = Depends(get_db)):
    client, _mock, _url = client_for(db)
    return campaign_stats(client, campaign_id)


@app.get("/api/campaigns/{campaign_id}")
def api_campaign(campaign_id: int, db: Session = Depends(get_db)):
    client, _mock, _url = client_for(db)
    try:
        return campaign_detail(client, campaign_id)
    except KeitaroError as exc:
        raise api_error(exc) from exc
