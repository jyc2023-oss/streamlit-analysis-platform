from __future__ import annotations

import logging
import signal
import sys
import threading
import time
from pathlib import Path
from queue import Empty, Queue

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import get_settings
from src.db import init_db
from src.parsers import SUPPORTED_EXTENSIONS
from src.services.datasets import index_dataset, scan_datasets

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
LOGGER = logging.getLogger("dataset-watcher")


class DatasetEventHandler(FileSystemEventHandler):
    def __init__(self, events: Queue[Path]) -> None:
        self.events = events

    def _enqueue(self, raw_path: str) -> None:
        path = Path(raw_path)
        if path.suffix.lower() in SUPPORTED_EXTENSIONS:
            self.events.put(path)

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._enqueue(event.src_path)

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._enqueue(event.src_path)

    def on_moved(self, event: FileSystemEvent) -> None:
        destination = getattr(event, "dest_path", "")
        if not event.is_directory and destination:
            self._enqueue(destination)


def main() -> None:
    settings = get_settings()
    init_db()
    stop_event = threading.Event()
    event_queue: Queue[Path] = Queue()
    pending: dict[Path, tuple[int, int, float] | None] = {}
    observer = Observer()
    handler = DatasetEventHandler(event_queue)

    def stop(_signum: int, _frame: object) -> None:
        stop_event.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    watched = 0
    for root in settings.data_roots:
        if root.is_dir():
            observer.schedule(handler, str(root), recursive=True)
            watched += 1
            LOGGER.info("watching %s", root)
        else:
            LOGGER.warning("data root is unavailable: %s", root)
    if not watched:
        raise RuntimeError("no readable data root is available")

    initial = scan_datasets(write_audit_log=False)
    LOGGER.info("initial index scan complete: %s", initial)
    observer.start()
    next_reconcile = time.monotonic() + settings.auto_index_reconcile_seconds

    try:
        while not stop_event.wait(0.5):
            while True:
                try:
                    path = event_queue.get_nowait()
                except Empty:
                    break
                pending.setdefault(path, None)

            now = time.monotonic()
            for path, previous in list(pending.items()):
                try:
                    stat = path.stat()
                except OSError:
                    pending.pop(path, None)
                    continue
                signature = (stat.st_size, stat.st_mtime_ns)
                if previous is None or previous[:2] != signature:
                    pending[path] = (*signature, now)
                    continue
                if now - previous[2] < settings.auto_index_stable_seconds:
                    continue
                status = index_dataset(path, require_stable=False)
                pending.pop(path, None)
                LOGGER.info("indexed %s (%s)", path, status)

            if now >= next_reconcile:
                result = scan_datasets(write_audit_log=False)
                LOGGER.info("periodic index reconciliation complete: %s", result)
                next_reconcile = now + settings.auto_index_reconcile_seconds
    finally:
        observer.stop()
        observer.join(timeout=10)


if __name__ == "__main__":
    main()
