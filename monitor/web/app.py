import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from monitor.config import Settings
from monitor.models import Event, Product, Snapshot, init_db
from monitor.notifiers import build_notifiers
from monitor.scheduler import create_scheduler
from monitor.scrapers import ADAPTERS, UnsupportedSiteError, get_adapter
from monitor.scrapers.fetch import Fetcher, make_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

HERE = Path(__file__).parent
DISPLAY_TZ = ZoneInfo("Asia/Taipei")

STATUS_LABELS = {
    "pending": "等待首次檢查",
    "ok": "正常",
    "network_error": "網路錯誤",
    "parse_error": "結構可能改版",
}
EVENT_LABELS = {
    "price_drop": "降價",
    "price_rise": "漲價",
    "out_of_stock": "缺貨",
    "restock": "補貨",
    "monitor_error": "監控異常",
    "monitor_recovered": "監控恢復",
}


def localtime(value: datetime | None) -> str:
    if value is None:
        return "—"
    return value.replace(tzinfo=UTC).astimezone(DISPLAY_TZ).strftime("%m/%d %H:%M:%S")


templates = Jinja2Templates(directory=HERE / "templates")
templates.env.filters["localtime"] = localtime
templates.env.filters["money"] = lambda v: f"NT${v:,}" if v is not None else "—"
templates.env.globals.update(
    STATUS_LABELS=STATUS_LABELS,
    EVENT_LABELS=EVENT_LABELS,
    ADAPTERS=ADAPTERS,
)


def add_product(session: Session, url: str, threshold_pct: float = 5.0) -> Product:
    """新增監控商品；網址不受支援時拋出 UnsupportedSiteError，重複時回傳既有商品。"""
    url = url.strip()
    adapter = get_adapter(url)
    existing = session.scalars(select(Product).where(Product.url == url)).first()
    if existing:
        return existing
    product = Product(url=url, shop=adapter.key, threshold_pct=threshold_pct)
    session.add(product)
    session.commit()
    return product


def latest_snapshots(session: Session) -> dict[int, Snapshot]:
    latest_ids = select(func.max(Snapshot.id)).group_by(Snapshot.product_id)
    snapshots = session.scalars(select(Snapshot).where(Snapshot.id.in_(latest_ids)))
    return {s.product_id: s for s in snapshots}


def create_app(settings: Settings | None = None, *, start_scheduler: bool = True) -> FastAPI:
    settings = settings or Settings.from_env()
    session_factory = init_db(settings.database_url)

    with session_factory() as session:
        if settings.seed_urls and not session.scalars(select(Product)).first():
            for url in settings.seed_urls:
                add_product(session, url)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if not start_scheduler:
            yield
            return
        async with make_client() as client:
            notifiers = build_notifiers(settings, client)
            logging.info("啟用的通知管道：%s", ", ".join(n.name for n in notifiers))
            scheduler = create_scheduler(
                settings.scrape_interval_minutes, session_factory, Fetcher(client), notifiers
            )
            scheduler.start()
            yield
            scheduler.shutdown(wait=False)

    app = FastAPI(title="競品價格監控", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")

    def render_products(request: Request, session: Session, error: str | None = None):
        products = session.scalars(select(Product).order_by(Product.id)).all()
        return templates.TemplateResponse(
            request,
            "_products.html",
            {"products": products, "latest": latest_snapshots(session), "error": error},
        )

    @app.get("/", response_class=HTMLResponse)
    def dashboard(request: Request):
        with session_factory() as session:
            products = session.scalars(select(Product).order_by(Product.id)).all()
            events = session.scalars(select(Event).order_by(Event.id.desc()).limit(10)).all()
            return templates.TemplateResponse(
                request,
                "dashboard.html",
                {
                    "products": products,
                    "latest": latest_snapshots(session),
                    "events": events,
                    "interval": settings.scrape_interval_minutes,
                    "error": None,
                },
            )

    @app.get("/partials/products", response_class=HTMLResponse)
    def products_partial(request: Request):
        with session_factory() as session:
            return render_products(request, session)

    @app.post("/products", response_class=HTMLResponse)
    def create_product(request: Request, url: str = Form(...), threshold_pct: float = Form(5.0)):
        with session_factory() as session:
            error = None
            try:
                add_product(session, url, threshold_pct)
            except UnsupportedSiteError as e:
                error = str(e)
            if request.headers.get("HX-Request"):
                return render_products(request, session, error)
        return RedirectResponse("/", status_code=303)

    @app.post("/products/{product_id}/delete", response_class=HTMLResponse)
    def delete_product(request: Request, product_id: int):
        with session_factory() as session:
            product = session.get(Product, product_id)
            if product:
                session.delete(product)
                session.commit()
            if request.headers.get("HX-Request"):
                return render_products(request, session)
        return RedirectResponse("/", status_code=303)

    @app.get("/products/{product_id}", response_class=HTMLResponse)
    def product_detail(request: Request, product_id: int):
        with session_factory() as session:
            product = session.get(Product, product_id)
            if product is None:
                raise HTTPException(404)
            chart = {
                "labels": [localtime(s.scraped_at) for s in product.snapshots],
                "prices": [s.price for s in product.snapshots],
                "stocks": [s.stock for s in product.snapshots],
            }
            return templates.TemplateResponse(
                request,
                "product.html",
                {
                    "product": product,
                    "chart": chart,
                    "latest": product.snapshots[-1] if product.snapshots else None,
                    "events": list(reversed(product.events)),
                },
            )

    @app.get("/events", response_class=HTMLResponse)
    def event_log(request: Request):
        with session_factory() as session:
            events = session.scalars(select(Event).order_by(Event.id.desc()).limit(200)).all()
            return templates.TemplateResponse(request, "events.html", {"events": events})

    return app
