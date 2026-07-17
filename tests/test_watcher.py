from pathlib import Path
from queue import Queue

from watchdog.events import FileCreatedEvent, FileModifiedEvent

from scripts.watch_datasets import DatasetEventHandler


def test_watcher_enqueues_supported_file_events(tmp_path: Path) -> None:
    events: Queue[Path] = Queue()
    handler = DatasetEventHandler(events)
    data_path = tmp_path / "new-data.bin"

    handler.on_created(FileCreatedEvent(str(data_path)))
    handler.on_modified(FileModifiedEvent(str(data_path)))

    assert events.get_nowait() == data_path
    assert events.get_nowait() == data_path


def test_watcher_ignores_unrelated_files(tmp_path: Path) -> None:
    events: Queue[Path] = Queue()
    handler = DatasetEventHandler(events)

    handler.on_created(FileCreatedEvent(str(tmp_path / "transfer.tmp")))

    assert events.empty()
