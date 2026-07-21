from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from src.analysis import AnalysisOutput
from src.analysis.arc_features import FEATURE_NAMES, ArcFeatureConfig, extract_arc_features
from src.analysis.arc_model import predict_arc
from src.services.datasets import load_channel

ArcChannelRef = tuple[int, str, str, str, int]


@dataclass
class _ChannelState:
    label: str
    values: np.ndarray
    half_starts: np.ndarray
    times: list[float] = field(default_factory=list)
    probabilities: list[float] = field(default_factory=list)
    features: list[np.ndarray] = field(default_factory=list)
    latest_waveform: list[float] = field(default_factory=list)


@dataclass
class _ArcTask:
    task_id: str
    channel_refs: tuple[ArcChannelRef, ...]
    sample_rate: float
    parameters: dict[str, Any]
    status: str = "waiting"
    phase: str = "等待启动"
    processed: int = 0
    total: int = 0
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    error: str | None = None
    channels: list[_ChannelState] = field(default_factory=list)
    output: AnalysisOutput | None = None
    cancelled: threading.Event = field(default_factory=threading.Event)
    lock: threading.RLock = field(default_factory=threading.RLock)


_TASKS: dict[str, _ArcTask] = {}
_TASKS_LOCK = threading.RLock()
_MAX_TASK_AGE_SECONDS = 60 * 60


def ensure_arc_stream_task(
    task_id: str,
    channel_refs: tuple[ArcChannelRef, ...],
    sample_rate: float,
    parameters: dict[str, Any],
) -> None:
    """Start a reusable background task if the same analysis is not already running."""
    with _TASKS_LOCK:
        _discard_expired_tasks_locked()
        if task_id in _TASKS:
            return
        task = _ArcTask(task_id, channel_refs, float(sample_rate), dict(parameters))
        _TASKS[task_id] = task
    threading.Thread(
        target=_run_task,
        args=(task,),
        name=f"arc-detection-{task_id[:8]}",
        daemon=True,
    ).start()


def get_arc_stream_snapshot(task_id: str) -> dict[str, Any]:
    with _TASKS_LOCK:
        task = _TASKS.get(task_id)
    if task is None:
        return {
            "task_id": task_id,
            "status": "missing",
            "phase": "检测任务不存在",
            "processed": 0,
            "total": 0,
            "channels": [],
            "error": None,
        }
    with task.lock:
        channels = [
            {
                "label": channel.label,
                "times": list(channel.times),
                "probabilities": list(channel.probabilities),
                "latest_waveform": list(channel.latest_waveform),
            }
            for channel in task.channels
        ]
        return {
            "task_id": task.task_id,
            "status": task.status,
            "phase": task.phase,
            "processed": task.processed,
            "total": task.total,
            "threshold": float(task.parameters.get("probability_threshold", 0.5)),
            "required_arc_halfwaves": int(
                task.parameters.get("required_arc_halfwaves", 3)
            ),
            "channels": channels,
            "error": task.error,
        }


def get_arc_stream_output(task_id: str) -> AnalysisOutput | None:
    with _TASKS_LOCK:
        task = _TASKS.get(task_id)
    if task is None:
        return None
    with task.lock:
        return task.output


def cancel_arc_stream_task(task_id: str) -> None:
    with _TASKS_LOCK:
        task = _TASKS.get(task_id)
    if task is not None:
        task.cancelled.set()


def _discard_expired_tasks_locked() -> None:
    now = time.time()
    expired = [
        task_id
        for task_id, task in _TASKS.items()
        if task.finished_at is not None and now - task.finished_at > _MAX_TASK_AGE_SECONDS
    ]
    for task_id in expired:
        del _TASKS[task_id]


def _preview(values: np.ndarray, maximum: int = 240) -> list[float]:
    if values.size <= maximum:
        return values.astype(float).tolist()
    indices = np.linspace(0, values.size - 1, maximum, dtype=np.int64)
    return values[indices].astype(float).tolist()


def _run_task(task: _ArcTask) -> None:
    try:
        half_points = int(round(task.sample_rate / 50.0)) // 2
        if half_points <= 0:
            raise ValueError("采样率无法生成有效的 50 Hz 半周波。")
        with task.lock:
            task.status = "reading"
            task.phase = "正在读取所选通道的完整数据"

        channel_states: list[_ChannelState] = []
        for dataset_id, _modified_at, channel, label, total_samples in task.channel_refs:
            if task.cancelled.is_set():
                _mark_cancelled(task)
                return
            values, _ = load_channel(dataset_id, channel, 0, total_samples)
            values = np.asarray(values, dtype=np.float64).reshape(-1)
            if values.size < half_points * 2:
                raise ValueError(f"{label} 至少需要一个完整的 50 Hz 周波。")
            starts = np.arange(0, values.size - half_points + 1, half_points, dtype=np.int64)
            channel_states.append(_ChannelState(label, values, starts))

        with task.lock:
            task.channels = channel_states
            task.total = sum(len(channel.half_starts) for channel in channel_states)
            task.status = "detecting"
            task.phase = "正在逐半周波提取特征并识别"

        config = ArcFeatureConfig(sample_rate=task.sample_rate)
        maximum_halfwaves = max(len(channel.half_starts) for channel in channel_states)
        for half_index in range(maximum_halfwaves):
            for channel in channel_states:
                if half_index >= len(channel.half_starts):
                    continue
                if task.cancelled.is_set():
                    _mark_cancelled(task)
                    return
                start = int(channel.half_starts[half_index])
                half_wave = channel.values[start : start + half_points]
                feature = extract_arc_features(half_wave, config)
                probability = float(predict_arc(feature.reshape(1, -1))[0])
                center_time = (start + half_points / 2) / task.sample_rate
                with task.lock:
                    channel.times.append(float(center_time))
                    channel.probabilities.append(probability)
                    channel.features.append(feature)
                    channel.latest_waveform = _preview(half_wave)
                    task.processed += 1

        output = _build_output(task, channel_states, half_points)
        with task.lock:
            task.output = output
            task.status = "completed"
            task.phase = "检测完成，完整结果已交回 Streamlit"
            task.finished_at = time.time()
    except Exception as exc:
        with task.lock:
            task.status = "error"
            task.phase = "检测失败"
            task.error = str(exc)
            task.finished_at = time.time()


def _mark_cancelled(task: _ArcTask) -> None:
    with task.lock:
        task.status = "cancelled"
        task.phase = "检测已取消"
        task.finished_at = time.time()


def _build_output(
    task: _ArcTask,
    channels: list[_ChannelState],
    half_points: int,
) -> AnalysisOutput:
    threshold = float(task.parameters.get("probability_threshold", 0.5))
    required = max(1, int(task.parameters.get("required_arc_halfwaves", 3)))
    series: list[tuple[str, np.ndarray, np.ndarray]] = []
    tables: list[pd.DataFrame] = []
    channel_results: list[dict[str, Any]] = []
    duration_seconds = 0.0

    for channel in channels:
        probabilities = np.asarray(channel.probabilities, dtype=np.float64)
        times = np.asarray(channel.times, dtype=np.float64)
        matrix = np.vstack(channel.features)
        predictions = probabilities >= threshold
        arc_count = int(predictions.sum())
        starts = channel.half_starts[: len(probabilities)]
        start_times = starts.astype(np.float64) / task.sample_rate
        end_times = (starts + half_points).astype(np.float64) / task.sample_rate
        table = pd.DataFrame(matrix, columns=FEATURE_NAMES)
        table.insert(0, "识别结果", np.where(predictions, "有弧", "无弧"))
        table.insert(0, "有弧概率", probabilities)
        table.insert(0, "结束时间_s", end_times)
        table.insert(0, "开始时间_s", start_times)
        table.insert(0, "半波序号", np.arange(1, len(table) + 1))
        table.insert(0, "通道", channel.label)
        tables.append(table)
        series.append((channel.label, times, probabilities))
        channel_duration = channel.values.size / task.sample_rate
        duration_seconds = max(duration_seconds, channel_duration)
        channel_results.append(
            {
                "label": channel.label,
                "folder_is_arc": arc_count >= required,
                "folder_result": "有弧" if arc_count >= required else "无弧",
                "arc_halfwaves": arc_count,
                "total_halfwaves": len(probabilities),
                "required_arc_halfwaves": required,
                "probability_threshold": threshold,
                "duration_seconds": channel_duration,
            }
        )

    arc_channels = sum(bool(item["folder_is_arc"]) for item in channel_results)
    folder_is_arc = arc_channels > 0
    folder_result = "有弧" if folder_is_arc else "无弧"
    first_x = series[0][1]
    first_y = series[0][2]
    return AnalysisOutput(
        f"文件夹判定：{folder_result} · {arc_channels}/{len(channels)} 个通道达到标准",
        first_x,
        first_y,
        "时间 (s)",
        "有弧概率",
        "arc_detection",
        pd.concat(tables, ignore_index=True),
        series=series,
        summary={
            "folder_is_arc": folder_is_arc,
            "folder_result": folder_result,
            "arc_channels": arc_channels,
            "total_channels": len(channel_results),
            "arc_halfwaves": sum(int(item["arc_halfwaves"]) for item in channel_results),
            "total_halfwaves": sum(int(item["total_halfwaves"]) for item in channel_results),
            "required_arc_halfwaves": required,
            "probability_threshold": threshold,
            "duration_seconds": duration_seconds,
            "channel_results": channel_results,
        },
    )
