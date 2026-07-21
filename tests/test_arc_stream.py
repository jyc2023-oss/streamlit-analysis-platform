from __future__ import annotations

import time

import numpy as np

from src.services import arc_stream


def test_arc_stream_processes_halfwaves_and_returns_complete_output(monkeypatch) -> None:
    values = np.arange(80, dtype=np.float64)
    monkeypatch.setattr(
        arc_stream,
        "load_channel",
        lambda dataset_id, channel, start, end: (values[start:end], 1_000.0),
    )
    monkeypatch.setattr(
        arc_stream,
        "extract_arc_features",
        lambda halfwave, config: np.full(24, float(np.mean(halfwave))),
    )
    monkeypatch.setattr(
        arc_stream,
        "predict_arc",
        lambda matrix: np.asarray([min(0.99, float(matrix[0, 0]) / 50)]),
    )

    task_id = f"test-{time.time_ns()}"
    arc_stream.ensure_arc_stream_task(
        task_id,
        ((1, "modified", "CH01", "2CH · CH02 · 2m主干", len(values)),),
        1_000.0,
        {"probability_threshold": 0.5, "required_arc_halfwaves": 3},
    )

    deadline = time.monotonic() + 3
    snapshot = arc_stream.get_arc_stream_snapshot(task_id)
    while snapshot["status"] not in {"completed", "error"} and time.monotonic() < deadline:
        time.sleep(0.01)
        snapshot = arc_stream.get_arc_stream_snapshot(task_id)

    assert snapshot["status"] == "completed", snapshot.get("error")
    assert snapshot["processed"] == snapshot["total"] == 8
    assert len(snapshot["channels"][0]["probabilities"]) == 8
    assert snapshot["channels"][0]["latest_waveform"]

    output = arc_stream.get_arc_stream_output(task_id)
    assert output is not None
    assert output.kind == "arc_detection"
    assert len(output.table) == 8
    assert output.summary is not None
    assert output.summary["folder_is_arc"] is True
    assert output.summary["total_channels"] == 1


def test_arc_stream_reuses_identical_task(monkeypatch) -> None:
    calls = 0

    def fake_load(*args):
        nonlocal calls
        calls += 1
        return np.arange(40, dtype=np.float64), 1_000.0

    monkeypatch.setattr(arc_stream, "load_channel", fake_load)
    monkeypatch.setattr(
        arc_stream,
        "extract_arc_features",
        lambda halfwave, config: np.zeros(24, dtype=np.float64),
    )
    monkeypatch.setattr(arc_stream, "predict_arc", lambda matrix: np.asarray([0.1]))
    task_id = f"reuse-{time.time_ns()}"
    arguments = (
        task_id,
        ((1, "modified", "CH01", "channel", 40),),
        1_000.0,
        {"probability_threshold": 0.5},
    )
    arc_stream.ensure_arc_stream_task(*arguments)
    arc_stream.ensure_arc_stream_task(*arguments)

    deadline = time.monotonic() + 3
    while (
        arc_stream.get_arc_stream_snapshot(task_id)["status"] not in {"completed", "error"}
        and time.monotonic() < deadline
    ):
        time.sleep(0.01)
    assert calls == 1
