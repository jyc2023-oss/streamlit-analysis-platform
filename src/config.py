from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")


def _resolve(value: str, base: Path = BASE_DIR) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def _data_roots(raw: str | None) -> tuple[Path, ...]:
    # 使用分号兼容 Windows 盘符；Linux 部署同样支持分号分隔。
    values = [item.strip() for item in (raw or "./sample_data").split(";") if item.strip()]
    return tuple(_resolve(item) for item in values)


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_env: str
    app_data_dir: Path
    data_roots: tuple[Path, ...]
    result_dir: Path
    cache_dir: Path
    temp_dir: Path
    database_path: Path
    result_retention_days: int
    max_scan_files: int
    max_preview_points: int
    max_analysis_samples: int
    session_idle_minutes: int
    auto_index_stable_seconds: int
    auto_index_reconcile_seconds: int
    sftp_enabled: bool
    sftp_host: str
    sftp_port: int
    sftp_username: str
    sftp_password: str
    sftp_private_key_path: Path | None
    sftp_private_key_passphrase: str
    sftp_remote_root: str
    sftp_sync_seconds: int
    sftp_cache_ttl_hours: int
    sftp_cache_max_bytes: int
    sftp_allow_unknown_host_key: bool

    def create_runtime_dirs(self) -> None:
        for path in (self.app_data_dir, self.result_dir, self.cache_dir, self.temp_dir):
            path.mkdir(parents=True, exist_ok=True)
        # 默认样例目录可以创建；外部配置目录只检查，不擅自创建。
        default_root = (BASE_DIR / "sample_data").resolve()
        if default_root in self.data_roots:
            default_root.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    data_dir = _resolve(os.getenv("APP_DATA_DIR", "./var"))
    key_value = os.getenv("SFTP_PRIVATE_KEY_PATH", "").strip()
    settings = Settings(
        app_name=os.getenv("APP_NAME", "服务器数据分析平台"),
        app_env=os.getenv("APP_ENV", "development"),
        app_data_dir=data_dir,
        data_roots=_data_roots(os.getenv("DATA_ROOTS")),
        result_dir=data_dir / "results",
        cache_dir=data_dir / "cache",
        temp_dir=data_dir / "temp",
        database_path=data_dir / "platform.sqlite3",
        result_retention_days=int(os.getenv("RESULT_RETENTION_DAYS", "30")),
        max_scan_files=int(os.getenv("MAX_SCAN_FILES", "10000")),
        max_preview_points=int(os.getenv("MAX_PREVIEW_POINTS", "5000")),
        max_analysis_samples=int(os.getenv("MAX_ANALYSIS_SAMPLES", "5000000")),
        session_idle_minutes=int(os.getenv("SESSION_IDLE_MINUTES", "120")),
        auto_index_stable_seconds=int(os.getenv("AUTO_INDEX_STABLE_SECONDS", "5")),
        auto_index_reconcile_seconds=int(os.getenv("AUTO_INDEX_RECONCILE_SECONDS", "300")),
        sftp_enabled=os.getenv("SFTP_ENABLED", "false").strip().lower() in {"1", "true", "yes"},
        sftp_host=os.getenv("SFTP_HOST", "").strip(),
        sftp_port=int(os.getenv("SFTP_PORT", "22")),
        sftp_username=os.getenv("SFTP_USERNAME", "").strip(),
        sftp_password=os.getenv("SFTP_PASSWORD", ""),
        sftp_private_key_path=_resolve(key_value) if key_value else None,
        sftp_private_key_passphrase=os.getenv("SFTP_PRIVATE_KEY_PASSPHRASE", ""),
        sftp_remote_root=os.getenv("SFTP_REMOTE_ROOT", "/").strip() or "/",
        sftp_sync_seconds=max(5, int(os.getenv("SFTP_SYNC_SECONDS", "30"))),
        sftp_cache_ttl_hours=max(1, int(os.getenv("SFTP_CACHE_TTL_HOURS", "24"))),
        sftp_cache_max_bytes=max(1, int(float(os.getenv("SFTP_CACHE_MAX_GB", "20")) * 1024**3)),
        sftp_allow_unknown_host_key=os.getenv("SFTP_ALLOW_UNKNOWN_HOST_KEY", "false")
        .strip()
        .lower()
        in {"1", "true", "yes"},
    )
    settings.create_runtime_dirs()
    return settings
