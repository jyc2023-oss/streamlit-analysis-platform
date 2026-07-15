from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt

from src.analysis import AnalysisOutput
from src.analysis.registry import ALGORITHM_VERSION
from src.config import get_settings
from src.db import audit, transaction, utc_now
from src.services.paths import ensure_allowed_result_path

plt.switch_backend("Agg")
plt.rcParams["font.sans-serif"] = [
    "Noto Sans CJK SC",
    "Microsoft YaHei",
    "SimHei",
    "DejaVu Sans",
]
plt.rcParams["axes.unicode_minus"] = False


def create_job(
    user_id: int,
    dataset_id: int,
    analysis_type: str,
    parameters: dict[str, Any],
) -> str:
    job_id = uuid.uuid4().hex
    with transaction() as connection:
        connection.execute(
            """INSERT INTO analysis_jobs
            (id, user_id, dataset_id, analysis_type, algorithm_version, parameters_json,
             status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'waiting', ?)""",
            (
                job_id,
                user_id,
                dataset_id,
                analysis_type,
                ALGORITHM_VERSION,
                json.dumps(parameters, ensure_ascii=False),
                utc_now(),
            ),
        )
    audit("job.created", user_id, "analysis_job", job_id, {"analysis_type": analysis_type})
    return job_id


def mark_running(job_id: str) -> None:
    with transaction() as connection:
        connection.execute(
            "UPDATE analysis_jobs SET status = 'running', started_at = ? WHERE id = ?",
            (utc_now(), job_id),
        )


def mark_failed(job_id: str, error: Exception) -> None:
    with transaction() as connection:
        connection.execute(
            """UPDATE analysis_jobs SET status = 'failed', error_message = ?, finished_at = ?
            WHERE id = ?""",
            (str(error)[:2000], utc_now(), job_id),
        )


def _write_figure(output: AnalysisOutput, path: Path, file_format: str) -> None:
    figure, axis = plt.subplots(figsize=(11, 5.5), constrained_layout=True)
    if output.kind == "bar":
        width = float(output.x[1] - output.x[0]) * 0.85 if output.x.size > 1 else 0.8
        axis.bar(output.x, output.y, width=width, color="#2563eb")
    else:
        axis.plot(output.x, output.y, color="#2563eb", linewidth=0.9)
    axis.set_title(output.title)
    axis.set_xlabel(output.x_label)
    axis.set_ylabel(output.y_label)
    axis.grid(True, alpha=0.25)
    figure.savefig(path, format=file_format, dpi=180)
    plt.close(figure)


def save_job_result(job_id: str, user_id: int, output: AnalysisOutput) -> list[dict[str, Any]]:
    now = datetime.now(UTC)
    result_dir = (
        get_settings().result_dir / str(now.year) / f"{now.month:02d}" / str(user_id) / job_id
    )
    result_dir.mkdir(parents=True, exist_ok=False)
    csv_path = result_dir / "result.csv"
    png_path = result_dir / "result.png"
    pdf_path = result_dir / "result.pdf"
    manifest_path = result_dir / "manifest.json"

    output.table.to_csv(csv_path, index=False, encoding="utf-8-sig")
    _write_figure(output, png_path, "png")
    _write_figure(output, pdf_path, "pdf")
    manifest_path.write_text(
        json.dumps(
            {
                "job_id": job_id,
                "algorithm_version": ALGORITHM_VERSION,
                "created_at": utc_now(),
                "title": output.title,
                "artifacts": ["result.csv", "result.png", "result.pdf"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    media_types = {
        csv_path: "text/csv",
        png_path: "image/png",
        pdf_path: "application/pdf",
        manifest_path: "application/json",
    }
    artifacts: list[dict[str, Any]] = []
    with transaction() as connection:
        for path, media_type in media_types.items():
            cursor = connection.execute(
                """INSERT INTO artifacts (job_id, name, path, media_type, size_bytes, created_at)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    job_id,
                    path.name,
                    str(path.resolve()),
                    media_type,
                    path.stat().st_size,
                    utc_now(),
                ),
            )
            artifacts.append(
                {
                    "id": int(cursor.lastrowid),
                    "job_id": job_id,
                    "name": path.name,
                    "path": str(path.resolve()),
                    "media_type": media_type,
                    "size_bytes": path.stat().st_size,
                }
            )
        connection.execute(
            """UPDATE analysis_jobs SET status = 'success', finished_at = ?, result_dir = ?
            WHERE id = ?""",
            (utc_now(), str(result_dir.resolve()), job_id),
        )
    audit("job.completed", user_id, "analysis_job", job_id)
    return artifacts


def list_jobs(user_id: int, is_admin: bool = False, limit: int = 100) -> list[dict[str, Any]]:
    where = "" if is_admin else "WHERE jobs.user_id = ?"
    parameters: tuple[Any, ...] = (limit,) if is_admin else (user_id, limit)
    with transaction() as connection:
        rows = connection.execute(
            f"""SELECT jobs.*, datasets.name AS dataset_name, users.username
            FROM analysis_jobs AS jobs
            JOIN datasets ON datasets.id = jobs.dataset_id
            JOIN users ON users.id = jobs.user_id
            {where}
            ORDER BY jobs.created_at DESC LIMIT ?""",
            parameters,
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["parameters"] = json.loads(item.pop("parameters_json"))
        result.append(item)
    return result


def get_artifacts(job_id: str, user_id: int, is_admin: bool = False) -> list[dict[str, Any]]:
    with transaction() as connection:
        job = connection.execute(
            "SELECT user_id FROM analysis_jobs WHERE id = ?", (job_id,)
        ).fetchone()
        if job is None or (not is_admin and job["user_id"] != user_id):
            raise PermissionError("无权访问该任务结果。")
        rows = connection.execute(
            "SELECT * FROM artifacts WHERE job_id = ? ORDER BY id", (job_id,)
        ).fetchall()
    return [dict(row) for row in rows]


def read_artifact(artifact: dict[str, Any]) -> bytes:
    return ensure_allowed_result_path(artifact["path"]).read_bytes()


def job_counts() -> dict[str, int]:
    with transaction() as connection:
        rows = connection.execute(
            "SELECT status, COUNT(*) AS count FROM analysis_jobs GROUP BY status"
        ).fetchall()
    counts = {"total": 0, "waiting": 0, "running": 0, "success": 0, "failed": 0}
    for row in rows:
        counts[row["status"]] = int(row["count"])
        counts["total"] += int(row["count"])
    return counts
