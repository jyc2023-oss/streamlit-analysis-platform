from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from src.config import get_settings
from src.db import audit, transaction, utc_now
from src.parsers import SUPPORTED_EXTENSIONS, read_channel, read_metadata
from src.services.paths import ensure_allowed_data_path


def _stable_file(path: Path, seconds: int = 5) -> bool:
    age = datetime.now(UTC).timestamp() - path.stat().st_mtime
    return age >= seconds


def scan_datasets(user_id: int | None = None) -> dict[str, int]:
    settings = get_settings()
    seen = 0
    ready = 0
    failed = 0
    now = utc_now()
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
                status = "pending"
                error_message = None
                metadata: dict[str, Any] = {}
                if _stable_file(path):
                    try:
                        metadata = read_metadata(path)
                        status = "ready"
                        ready += 1
                    except Exception as exc:
                        status = "error"
                        error_message = str(exc)[:1000]
                        failed += 1
                stat = path.stat()
                resolved = path.resolve()
                connection.execute(
                    """INSERT INTO datasets
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
                      metadata_json=excluded.metadata_json""",
                    (
                        str(resolved),
                        str(root.resolve()),
                        str(resolved.relative_to(root.resolve())),
                        path.name,
                        path.suffix.lower(),
                        stat.st_size,
                        datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
                        now,
                        status,
                        error_message,
                        json.dumps(metadata, ensure_ascii=False),
                    ),
                )
    audit(
        "datasets.scanned", user_id=user_id, detail={"seen": seen, "ready": ready, "failed": failed}
    )
    return {"seen": seen, "ready": ready, "failed": failed}


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
    path = ensure_allowed_data_path(dataset["path"])
    return read_channel(path, channel, start, end)


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
