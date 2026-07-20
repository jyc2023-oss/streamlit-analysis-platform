from __future__ import annotations

import logging
import signal
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import get_settings
from src.db import init_db
from src.services.datasets import sync_remote_datasets
from src.services.sftp import cleanup_sftp_cache

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOGGER = logging.getLogger("sftp-sync")


def main() -> None:
    settings = get_settings()
    if not settings.sftp_enabled:
        raise RuntimeError("请先设置 SFTP_ENABLED=true。")
    init_db()
    stopped = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stopped.set())
    signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    while not stopped.is_set():
        try:
            result = sync_remote_datasets()
            cleaned = cleanup_sftp_cache(settings)
            LOGGER.info("SFTP index synchronized: %s; cache cleaned: %s", result, cleaned)
        except Exception:
            LOGGER.exception("SFTP synchronization failed")
        stopped.wait(settings.sftp_sync_seconds)


if __name__ == "__main__":
    main()
