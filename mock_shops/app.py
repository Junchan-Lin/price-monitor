"""模擬競品商城：依 Host 分流成三家 HTML 結構不同的商城，並定時隨機變動價格與庫存。"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from mock_shops.catalog import SHOPS, ShopState

logger = logging.getLogger("mock_shops")

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
state = ShopState()


async def mutate_periodically(interval: float) -> None:
    while True:
        await asyncio.sleep(interval)
        for change in state.mutate():
            logger.info("商品變動：%s", change)


@asynccontextmanager
async def lifespan(app: FastAPI):
    interval = float(os.environ.get("MOCK_CHANGE_INTERVAL_SECONDS", "180"))
    task = asyncio.create_task(mutate_periodically(interval)) if interval > 0 else None
    yield
    if task:
        task.cancel()


app = FastAPI(title="Mock Shops", lifespan=lifespan)


def shop_of(request: Request) -> str | None:
    """以 Host 的第一段判斷是哪一家商城，例如 shop-a.localhost → shop-a。"""
    label = (request.url.hostname or "").split(".")[0]
    return label if label in SHOPS else None


def render(request: Request, template: str, shop: str, **context) -> HTMLResponse:
    return templates.TemplateResponse(
        request, template, {"shop": shop, "shop_name": SHOPS[shop], **context}
    )


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    shop = shop_of(request)
    if shop is None:
        port = request.url.port
        return templates.TemplateResponse(
            request, "index.html", {"shops": SHOPS, "state": state, "port": port}
        )
    if shop == "shop-c":
        return render(request, "shop_c_index.html", shop, items=state.items[shop].values())
    return RedirectResponse("/products")


@app.get("/products", response_class=HTMLResponse)
def product_list(request: Request):
    shop = shop_of(request)
    if shop not in ("shop-a", "shop-b"):
        raise HTTPException(404)
    items = list(state.items[shop].values())
    if state.redesigned[shop]:
        return render(request, "redesigned.html", shop, items=items)
    return render(request, f"{shop.replace('-', '_')}.html", shop, items=items)


@app.get("/item/{sku}", response_class=HTMLResponse)
def product_detail(request: Request, sku: str):
    shop = shop_of(request)
    if shop != "shop-c" or sku not in state.items[shop]:
        raise HTTPException(404)
    item = state.items[shop][sku]
    if state.redesigned[shop]:
        return render(request, "redesigned.html", shop, items=[item])
    return render(request, "shop_c.html", shop, item=item)


# ---- 管理端點：錄製 demo 時手動觸發變動，不必等排程 ----


class ItemUpdate(BaseModel):
    price: int | None = None
    stock: int | None = None


@app.post("/admin/mutate")
def admin_mutate(request: Request):
    changes = state.mutate()
    if "text/html" in request.headers.get("accept", ""):
        return RedirectResponse("/", status_code=303)
    return {"changes": changes}


@app.post("/admin/items/{shop}/{sku}")
def admin_set(shop: str, sku: str, update: ItemUpdate):
    if shop not in SHOPS or sku not in state.items[shop]:
        raise HTTPException(404)
    item = state.set(shop, sku, price=update.price, stock=update.stock)
    return {"shop": shop, "sku": sku, "price": item.price, "stock": item.stock}


@app.post("/admin/redesign/{shop}")
def admin_redesign(request: Request, shop: str, enabled: bool = True):
    """切換成改版後的 HTML 結構，用來展示監控端能偵測到網站改版。"""
    if shop not in SHOPS:
        raise HTTPException(404)
    state.redesigned[shop] = enabled
    if "text/html" in request.headers.get("accept", ""):
        return RedirectResponse("/", status_code=303)
    return {"shop": shop, "redesigned": enabled}


@app.post("/admin/reset")
def admin_reset():
    state.reset()
    return {"ok": True}
