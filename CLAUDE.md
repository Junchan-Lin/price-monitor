# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

逅斯蓋工作室（Code Sky）作品集作品：競品價格監控與通知。設計依據是 [docs/design.md](docs/design.md)，偏離設計前先提出。README 以客戶角度撰寫（問題、解法、成果、技術、對應服務方案）。

## 指令

- `uv sync`：安裝套件（Python 3.12，`package = false`，直接以 `monitor` / `mock_shops` 模組執行）
- `uv run pytest`；單一測試：`uv run pytest tests/test_detector.py::test_price_threshold_boundary`
- `uv run ruff check . && uv run ruff format .`
- `docker compose up`：monitor :8000、mock-shops :8001。demo 時在 `.env` 設定 `SCRAPE_INTERVAL_MINUTES=1`
- 本機單獨執行：`uv run uvicorn --factory monitor.web.app:create_app --port 8000`、`uv run uvicorn mock_shops.app:app --port 8001`

## 架構重點

- **網址決定 adapter**：`monitor/scrapers/__init__.py:get_adapter` 依序呼叫各 adapter 的 `matches(hostname)`。預設比對網域的第一段（`shop-a.localhost` → `shop-a`）；真實網站要覆寫 `matches`，用完整網域比對（例如 PChome）。mock-shops 用同樣規則依 Host 分流成三家商城；compose 用 network alias 讓容器內與本機瀏覽器使用同一組網址。
- **兩種 adapter**：`HtmlAdapter` 抓網址本身的 HTML，再交給 `_parse(soup, url)` 解析（三家模擬商城）。直接繼承 `Adapter` 的要自己實作 `scrape(url, fetcher)`，可以改抓其他網址，例如 `PChomeAdapter` 會把商品頁網址轉成價格 API（`ecapi-cdn`）與搜尋 API（取名稱）。解析時用 `parse_errors()` 包起來，讓意外例外變成 ParseError。
- A、B 只有列表頁，商品網址用錨點指定（`/products#P001`）；C 是詳細頁（`/item/P001`）。
- **PChome**：商品頁 HTML 會擋非瀏覽器的請求（回 429），所以改用 API。售價取 `Price.P`；`ButtonType != "ForSale"`（缺貨時是 `OrderRefill`）時庫存視為 0。這些是沒有公開文件的內部 API，格式改變時應該產生 ParseError，不可以默默回傳錯誤值。
- **一輪排程**（`monitor/scheduler.py:run_cycle`）：逐一處理商品並逐一 commit → `adapter.scrape`（內部透過 `Fetcher.get`：重試 3 次、間隔遞增、同一 host 間隔 1 秒）→ 存 Snapshot → `detector.detect` → Event → `notifiers.dispatch_pending`。
- **錯誤分類**：`FetchError` 對應 `network_error`，`ParseError` 對應 `parse_error`（網站可能改版）。
- **通知**：Notifier 是 Protocol（`name` + `async send(event)`，失敗時拋出例外；HTTP 失敗一律轉成 `NotifyError`，訊息與日誌都不含網址，因為 Telegram 網址帶有 bot token）。`EventDelivery` 在每個事件、每個管道各有一筆，已成功的管道不會重送；所有管道都成功才設定 `Event.notified_at`。沒有設定 Telegram 與 LINE 時，改用 ConsoleNotifier。
- **web**：`create_app(settings, start_scheduler=...)` 是 factory。HTMX 請求（`HX-Request` header）回傳 `_products.html` 片段，其他請求回傳 303 redirect。資料庫是空的時，會依 `SEED_URLS` 建立預設的監控商品。
- 時間以 naive UTC 存入資料庫，顯示時透過 `localtime` filter 轉成 Asia/Taipei。

## 容易出錯的規則

- 價格變動 **≥** 門檻才產生事件，用整數運算比較，避免浮點誤差。缺貨與補貨不受門檻影響。第一筆快照只建立基準。
- `monitor_error` 只在 `consecutive_failures == 3` 那一次產生；恢復時，若先前失敗次數 ≥ 3，產生 `monitor_recovered`。

## 測試

- `tests/fixtures/*.html` 是由 mock-shops 渲染出來的。修改 mock 商城模板或 `catalog.py` 的價格後，要重新產生這些 fixture，並更新 `test_scrapers.py` 的預期值。`*_redesigned.html` 用來驗證改版時會拋出 ParseError。
- 整合測試透過 `httpx.ASGITransport` 在同一個程序內跑 mock-shops，並直接操作 `mock_shops.app.state` 來製造變化。
- 測試中不得呼叫真實的 Telegram、LINE 或 PChome，HTTP 一律用 respx 模擬。PChome 的 API 回應存成 `tests/fixtures/pchome_*.json`。
