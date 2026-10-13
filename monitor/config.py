import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    scrape_interval_minutes: float = 10
    database_url: str = "sqlite:///data/monitor.db"
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    line_channel_access_token: str = ""
    line_user_id: str = ""
    # 資料庫沒有任何商品時，預先建立的監控網址（逗號分隔）
    seed_urls: list[str] = field(default_factory=list)

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.environ.get
        return cls(
            scrape_interval_minutes=float(env("SCRAPE_INTERVAL_MINUTES") or 10),
            database_url=env("DATABASE_URL") or cls.database_url,
            telegram_bot_token=env("TELEGRAM_BOT_TOKEN", ""),
            telegram_chat_id=env("TELEGRAM_CHAT_ID", ""),
            line_channel_access_token=env("LINE_CHANNEL_ACCESS_TOKEN", ""),
            line_user_id=env("LINE_USER_ID", ""),
            seed_urls=[u.strip() for u in env("SEED_URLS", "").split(",") if u.strip()],
        )
