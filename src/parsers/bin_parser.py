from __future__ import annotations

import struct
from pathlib import Path
from typing import Any

import numpy as np

HEADER_SIZE = 56
SAMPLE_DTYPE = np.dtype("<f8")


def _parse_header(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        header = handle.read(HEADER_SIZE)
    if len(header) < HEADER_SIZE:
        raise ValueError("BIN 文件头不足 56 字节。")
    raw_device = header[:32].split(b"\0", 1)[0]
    device_name = raw_device.decode("utf-8", errors="replace").strip() or "Unknown"
    timestamp_ms = struct.unpack("<Q", header[32:40])[0]
    channels = struct.unpack("<I", header[40:44])[0]
    sample_rate = struct.unpack("<I", header[44:48])[0]
    declared_samples = struct.unpack("<I", header[48:52])[0]
    if not 1 <= channels <= 256:
        raise ValueError(f"无效通道数：{channels}")
    if sample_rate <= 0:
        raise ValueError(f"无效采样率：{sample_rate}")
    available_values = max(0, path.stat().st_size - HEADER_SIZE) // SAMPLE_DTYPE.itemsize
    available_samples = available_values // channels
    total_samples = (
        min(declared_samples, available_samples) if declared_samples else available_samples
    )
    if total_samples <= 0:
        raise ValueError("BIN 文件中没有可读取的采样数据。")
    return {
        "device_name": device_name,
        "timestamp_ms": int(timestamp_ms),
        "channels_count": int(channels),
        "sample_rate": int(sample_rate),
        "total_samples": int(total_samples),
        "declared_samples": int(declared_samples),
    }


def bin_metadata(path: Path) -> dict[str, Any]:
    metadata = _parse_header(path)
    metadata["channels"] = [f"CH{index + 1:02d}" for index in range(metadata["channels_count"])]
    metadata["duration_seconds"] = metadata["total_samples"] / metadata["sample_rate"]
    metadata["format"] = "bin-float64-le-v1"
    return metadata


def read_bin_channel(
    path: Path,
    channel: str,
    start: int = 0,
    end: int | None = None,
) -> tuple[np.ndarray, float]:
    metadata = _parse_header(path)
    try:
        index = metadata_channels(metadata).index(channel)
    except ValueError as exc:
        raise ValueError(f"通道不存在：{channel}") from exc
    total = metadata["total_samples"]
    start = max(0, int(start))
    end = total if end is None else min(total, int(end))
    if start >= end:
        raise ValueError("采样区间为空。")
    mapped = np.memmap(
        path,
        dtype=SAMPLE_DTYPE,
        mode="r",
        offset=HEADER_SIZE,
        shape=(total, metadata["channels_count"]),
    )
    values = np.asarray(mapped[start:end, index], dtype=np.float64).copy()
    return values, float(metadata["sample_rate"])


def metadata_channels(metadata: dict[str, Any]) -> list[str]:
    return [f"CH{index + 1:02d}" for index in range(metadata["channels_count"])]
