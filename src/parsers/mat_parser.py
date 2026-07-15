from __future__ import annotations

from pathlib import Path
from typing import Any

import h5py
import numpy as np
from scipy.io import loadmat, whosmat


def _is_hdf5(path: Path) -> bool:
    return h5py.is_hdf5(path)


def _is_waveform_shape(shape: tuple[int, ...]) -> bool:
    return bool(shape) and int(np.prod(shape)) > 1


def mat_metadata(path: Path) -> dict[str, Any]:
    channels: list[str] = []
    shapes: dict[str, list[int]] = {}
    if _is_hdf5(path):
        with h5py.File(path, "r") as handle:

            def visitor(name: str, obj: h5py.Dataset) -> None:
                if isinstance(obj, h5py.Dataset) and np.issubdtype(obj.dtype, np.number):
                    shape = tuple(int(value) for value in obj.shape)
                    if _is_waveform_shape(shape):
                        channels.append(name)
                        shapes[name] = list(shape)

            handle.visititems(visitor)
        mat_version = "7.3/HDF5"
    else:
        for name, shape, dtype in whosmat(path):
            numeric_hint = not any(token in dtype.lower() for token in ("char", "cell", "struct"))
            if numeric_hint and _is_waveform_shape(tuple(shape)):
                channels.append(name)
                shapes[name] = [int(value) for value in shape]
        mat_version = "5"
    if not channels:
        raise ValueError("MAT 文件中没有找到可绘制的数值数组。")
    return {
        "format": f"mat-v{mat_version}",
        "channels": sorted(channels, key=str.casefold),
        "shapes": shapes,
        "channels_count": len(channels),
        "sample_rate": None,
        "total_samples": max(int(np.prod(shapes[name])) for name in channels),
    }


def read_mat_channel(
    path: Path,
    channel: str,
    start: int = 0,
    end: int | None = None,
) -> tuple[np.ndarray, None]:
    if _is_hdf5(path):
        with h5py.File(path, "r") as handle:
            if channel not in handle or not isinstance(handle[channel], h5py.Dataset):
                raise ValueError(f"通道不存在：{channel}")
            values = np.asarray(handle[channel]).reshape(-1)
    else:
        content = loadmat(path, variable_names=[channel], squeeze_me=True)
        if channel not in content:
            raise ValueError(f"通道不存在：{channel}")
        values = np.asarray(content[channel]).reshape(-1)
    if not np.issubdtype(values.dtype, np.number):
        raise ValueError(f"通道 {channel} 不是数值数组。")
    start = max(0, int(start))
    end = len(values) if end is None else min(len(values), int(end))
    if start >= end:
        raise ValueError("采样区间为空。")
    return np.asarray(values[start:end], dtype=np.float64), None
