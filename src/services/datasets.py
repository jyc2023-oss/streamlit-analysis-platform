from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

import numpy as np

from src.config import get_settings
from src.db import audit, transaction, utc_now
from src.parsers import SUPPORTED_EXTENSIONS, read_channel, read_metadata
from src.services.paths import ensure_allowed_data_path
from src.services.sftp import (
    is_remote_uri,
    materialize_remote_dataset,
    remote_uri,
    scan_remote_entries,
)


def _stable_file(path: Path, seconds: int = 5) -> bool:
    age = datetime.now(UTC).timestamp() - path.stat().st_mtime
    return age >= seconds


def _root_for_path(path: Path, roots: tuple[Path, ...]) -> Path | None:
    resolved = path.resolve()
    return next((root.resolve() for root in roots if resolved.is_relative_to(root.resolve())), None)


def index_dataset(
    path: Path,
    require_stable: bool = True,
    *,
    connection: sqlite3.Connection | None = None,
) -> str | None:
    """Insert or update one supported data file and return its resulting status."""
    settings = get_settings()
    path = Path(path)
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        return None
    try:
        if not path.is_file():
            return None
        root = _root_for_path(path, settings.data_roots)
        if root is None:
            return None
        stat = path.stat()
    except OSError:
        return None

    status = "pending"
    error_message = None
    metadata: dict[str, Any] = {}
    if not require_stable or _stable_file(path, settings.auto_index_stable_seconds):
        try:
            metadata = read_metadata(path)
            status = "ready"
        except Exception as exc:
            status = "error"
            error_message = str(exc)[:1000]

    resolved = path.resolve()
    statement = """INSERT INTO datasets
            (path, root_path, relative_path, name, extension, size_bytes, modified_at,
             indexed_at, status, error_message, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
              root_path=excluded.root_path,
              relative_path=excluded.relative_path,
              name=excluded.name,
              extension=excluded.extension,
              size_bytes=excluded.size_bytes,
              modified_at=excluded.modified_at,
              indexed_at=excluded.indexed_at,
              status=excluded.status,
              error_message=excluded.error_message,
              metadata_json=excluded.metadata_json
            WHERE datasets.root_path IS NOT excluded.root_path
               OR datasets.relative_path IS NOT excluded.relative_path
               OR datasets.name IS NOT excluded.name
               OR datasets.extension IS NOT excluded.extension
               OR datasets.size_bytes IS NOT excluded.size_bytes
               OR datasets.modified_at IS NOT excluded.modified_at
               OR datasets.status IS NOT excluded.status
               OR datasets.error_message IS NOT excluded.error_message
               OR datasets.metadata_json IS NOT excluded.metadata_json"""
    values = (
        str(resolved),
        str(root),
        str(resolved.relative_to(root)),
        path.name,
        path.suffix.lower(),
        stat.st_size,
        datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
        utc_now(),
        status,
        error_message,
        json.dumps(metadata, ensure_ascii=False),
    )
    if connection is not None:
        connection.execute(statement, values)
    else:
        with transaction() as own_connection:
            own_connection.execute(statement, values)
    return status


def scan_datasets(
    user_id: int | None = None, *, write_audit_log: bool = True
) -> dict[str, int]:
    settings = get_settings()
    seen = 0
    ready = 0
    failed = 0
    with transaction() as connection:
        for root in settings.data_roots:
            if not root.exists() or not root.is_dir():
                continue
            for path in root.rglob("*"):
                if seen >= settings.max_scan_files:
                    break
                if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                    continue
                seen += 1
                status = index_dataset(path, connection=connection)
                ready += int(status == "ready")
                failed += int(status == "error")
    remote_result = {"seen": 0, "ready": 0, "failed": 0}
    if settings.sftp_enabled:
        remote_result = sync_remote_datasets()
        seen += remote_result["seen"]
        ready += remote_result["ready"]
        failed += remote_result["failed"]
    if write_audit_log:
        audit(
            "datasets.scanned",
            user_id=user_id,
            detail={"seen": seen, "ready": ready, "failed": failed},
        )
    return {"seen": seen, "ready": ready, "failed": failed}


def sync_remote_datasets() -> dict[str, int]:
    """Refresh the SQLite catalog from SFTP without downloading complete data files."""
    settings = get_settings()
    if not settings.sftp_enabled:
        return {"seen": 0, "ready": 0, "failed": 0}
    root_uri = remote_uri(settings.sftp_remote_root, settings)
    with transaction() as connection:
        existing_rows = connection.execute(
            "SELECT * FROM datasets WHERE root_path = ?", (root_uri,)
        ).fetchall()
    known_entries = {
        row["path"]: {
            "size_bytes": row["size_bytes"],
            "modified_at": row["modified_at"],
            "metadata": json.loads(row["metadata_json"] or "{}"),
            "error_message": row["error_message"],
            "status": row["status"],
        }
        for row in existing_rows
    }
    entries = scan_remote_entries(settings, known_entries)
    indexed_at = utc_now()
    seen_uris = {entry.uri for entry in entries}
    statement = """INSERT INTO datasets
        (path, root_path, relative_path, name, extension, size_bytes, modified_at,
         indexed_at, status, error_message, metadata_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(path) DO UPDATE SET
          root_path=excluded.root_path,
          relative_path=excluded.relative_path,
          name=excluded.name,
          extension=excluded.extension,
          size_bytes=excluded.size_bytes,
          modified_at=excluded.modified_at,
          indexed_at=CASE
            WHEN datasets.size_bytes=excluded.size_bytes
             AND datasets.modified_at=excluded.modified_at
             AND datasets.status=excluded.status
            THEN datasets.indexed_at ELSE excluded.indexed_at END,
          status=excluded.status,
          error_message=excluded.error_message,
          metadata_json=CASE
            WHEN datasets.modified_at=excluded.modified_at
             AND json_extract(datasets.metadata_json, '$.metadata_pending') IS NULL
            THEN datasets.metadata_json ELSE excluded.metadata_json END"""
    with transaction() as connection:
        for entry in entries:
            known = known_entries.get(entry.uri)
            unchanged = (
                known is not None
                and int(known["size_bytes"]) == entry.size_bytes
                and str(known["modified_at"]) == entry.modified_at
            )
            status = "error" if entry.error_message else ("ready" if unchanged else "pending")
            connection.execute(
                statement,
                (
                    entry.uri,
                    entry.root_uri,
                    entry.relative_path,
                    entry.name,
                    entry.extension,
                    entry.size_bytes,
                    entry.modified_at,
                    indexed_at,
                    status,
                    entry.error_message,
                    json.dumps(entry.metadata, ensure_ascii=False),
                ),
            )
        rows = connection.execute(
            "SELECT path FROM datasets WHERE root_path = ?", (root_uri,)
        ).fetchall()
        missing = [row["path"] for row in rows if row["path"] not in seen_uris]
        connection.executemany(
            """UPDATE datasets SET status='missing', error_message='远程文件已不存在。',
            indexed_at=? WHERE path=? AND status!='missing'""",
            ((indexed_at, path) for path in missing),
        )
    failed = sum(entry.error_message is not None for entry in entries)
    return {"seen": len(entries), "ready": len(entries) - failed, "failed": failed}


def list_datasets(search: str = "", status: str | None = None) -> list[dict[str, Any]]:
    clauses = []
    parameters: list[Any] = []
    if search:
        clauses.append("(name LIKE ? OR relative_path LIKE ?)")
        parameters.extend([f"%{search}%", f"%{search}%"])
    if status:
        clauses.append("status = ?")
        parameters.append(status)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with transaction() as connection:
        rows = connection.execute(
            f"SELECT * FROM datasets {where} ORDER BY modified_at DESC", parameters
        ).fetchall()
    return [_decode_dataset(dict(row)) for row in rows]


def get_dataset(dataset_id: int) -> dict[str, Any] | None:
    with transaction() as connection:
        row = connection.execute("SELECT * FROM datasets WHERE id = ?", (dataset_id,)).fetchone()
    return _decode_dataset(dict(row)) if row else None


def _decode_dataset(row: dict[str, Any]) -> dict[str, Any]:
    row["metadata"] = json.loads(row.pop("metadata_json") or "{}")
    return row


def load_channel(
    dataset_id: int, channel: str, start: int, end: int
) -> tuple[np.ndarray, float | None]:
    dataset = get_dataset(dataset_id)
    if not dataset or dataset["status"] != "ready":
        raise ValueError("数据不存在或尚不可用。")
    path = (
        materialize_remote_dataset(dataset)
        if is_remote_uri(str(dataset["path"]))
        else ensure_allowed_data_path(dataset["path"])
    )
    return read_channel(path, channel, start, end)


def hydrate_dataset_metadata(dataset_id: int) -> dict[str, Any]:
    """Download a remote MAT file on first use and persist its parsed variables."""
    dataset = get_dataset(dataset_id)
    if not dataset or dataset["status"] != "ready":
        raise ValueError("数据不存在或尚不可用。")
    if not dataset["metadata"].get("metadata_pending"):
        return dataset
    if not is_remote_uri(str(dataset["path"])):
        return dataset
    try:
        local_path = materialize_remote_dataset(dataset)
        metadata = read_metadata(local_path)
    except Exception as exc:
        with transaction() as connection:
            connection.execute(
                "UPDATE datasets SET status='error', error_message=?, indexed_at=? WHERE id=?",
                (str(exc)[:1000], utc_now(), dataset_id),
            )
        raise
    with transaction() as connection:
        connection.execute(
            "UPDATE datasets SET metadata_json=?, error_message=NULL, indexed_at=? WHERE id=?",
            (json.dumps(metadata, ensure_ascii=False), utc_now(), dataset_id),
        )
    return get_dataset(dataset_id) or dataset


def downsample(values: np.ndarray, max_points: int) -> tuple[np.ndarray, np.ndarray]:
    values = np.asarray(values, dtype=np.float64)
    if values.size <= max_points:
        indices = np.arange(values.size)
        return indices, values
    # 每个桶保留最小值和最大值，兼顾尖峰与趋势。
    bucket_count = max(1, max_points // 2)
    edges = np.linspace(0, values.size, bucket_count + 1, dtype=int)
    selected: list[int] = []
    for left, right in zip(edges[:-1], edges[1:], strict=True):
        if right <= left:
            continue
        chunk = values[left:right]
        local = [left + int(np.argmin(chunk)), left + int(np.argmax(chunk))]
        selected.extend(sorted(set(local)))
    indices = np.asarray(sorted(set(selected)), dtype=int)
    return indices, values[indices]


def dataset_path_parts(dataset: dict[str, Any]) -> tuple[str, ...]:
    """Return normalized relative-path parts without changing displayed folder names."""
    relative_path = str(dataset.get("relative_path", "")).replace("\\", "/")
    return tuple(PurePosixPath(relative_path).parts)


def filter_datasets_by_folder(
    datasets: list[dict[str, Any]], folder_parts: tuple[str, ...]
) -> list[dict[str, Any]]:
    """Keep datasets located in the selected folder or one of its descendants."""
    if not folder_parts:
        return list(datasets)
    return [
        item for item in datasets if dataset_path_parts(item)[: len(folder_parts)] == folder_parts
    ]


def folder_choices(
    datasets: list[dict[str, Any]],
    folder_parts: tuple[str, ...],
    required_channel_counts: set[int] | None = None,
) -> list[str]:
    """List immediate child folders whose descendants satisfy the channel requirements."""
    scoped = filter_datasets_by_folder(datasets, folder_parts)
    depth = len(folder_parts)
    children = sorted(
        {parts[depth] for item in scoped if len(parts := dataset_path_parts(item)) > depth + 1},
        key=lambda value: value.strip().casefold(),
    )
    if not required_channel_counts:
        return children
    eligible = []
    for child in children:
        child_items = filter_datasets_by_folder(datasets, (*folder_parts, child))
        counts = {int(item["metadata"].get("channels_count", 0)) for item in child_items}
        if required_channel_counts.issubset(counts):
            eligible.append(child)
    return eligible


def _dataset_pair_scope(dataset: dict[str, Any]) -> tuple[str, ...]:
    """Return the common acquisition folder above optional 114/116 subfolders."""
    parent = dataset_path_parts(dataset)[:-1]
    if parent and any(number in parent[-1].casefold() for number in ("114", "116")):
        return parent[:-1]
    return parent


def latest_complete_dataset_pair(
    datasets: list[dict[str, Any]],
) -> tuple[tuple[str, ...], dict[str, Any], dict[str, Any]] | None:
    """Return the newest ready acquisition containing both an 114 and 116 file."""
    grouped: dict[tuple[str, ...], dict[int, list[dict[str, Any]]]] = {}
    for dataset in datasets:
        if dataset.get("status", "ready") != "ready":
            continue
        channels = int(dataset.get("metadata", {}).get("channels_count", 0))
        if channels not in {2, 8}:
            continue
        grouped.setdefault(_dataset_pair_scope(dataset), {8: [], 2: []})[channels].append(dataset)

    candidates = []
    for scope, channel_groups in grouped.items():
        if not channel_groups[8] or not channel_groups[2]:
            continue
        selected_8 = max(channel_groups[8], key=lambda item: str(item["modified_at"]))
        selected_2 = max(channel_groups[2], key=lambda item: str(item["modified_at"]))
        completed_at = min(str(selected_8["modified_at"]), str(selected_2["modified_at"]))
        candidates.append((completed_at, scope, selected_8, selected_2))
    if not candidates:
        return None
    _completed_at, scope, selected_8, selected_2 = max(candidates, key=lambda item: item[0])
    return scope, selected_8, selected_2


def dataset_counts() -> dict[str, int]:
    with transaction() as connection:
        rows = connection.execute(
            "SELECT status, COUNT(*) AS count FROM datasets GROUP BY status"
        ).fetchall()
    counts = {"total": 0, "ready": 0, "pending": 0, "error": 0}
    for row in rows:
        counts[row["status"]] = int(row["count"])
        counts["total"] += int(row["count"])
    return counts


def dataset_catalog_revision() -> tuple[int, int, str]:
    """Return a cheap revision token that changes when indexed files change."""
    with transaction() as connection:
        row = connection.execute(
            """SELECT COUNT(*) AS total, COALESCE(MAX(id), 0) AS max_id,
            COALESCE(MAX(indexed_at), '') AS latest_indexed FROM datasets"""
        ).fetchone()
    return int(row["total"]), int(row["max_id"]), str(row["latest_indexed"])
