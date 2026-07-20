from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pywt

FEATURE_NAMES = [
    "平均绝对值", "均方根", "峰值", "均值", "方差", "偏度", "峭度",
    "波形因子", "峰值因子", "脉冲因子",
    *[f"D{i}能量占比" for i in range(1, 7)], "A6能量占比",
    *[f"D{i}平均绝对值占比" for i in range(1, 7)], "A6平均绝对值占比",
]


@dataclass(frozen=True)
class ArcFeatureConfig:
    sample_rate: float
    window_ms: float = 1.0
    wavelet: str = "db4"
    level: int = 6
    eps: float = 1e-12


def _time_features(values: np.ndarray, eps: float) -> np.ndarray:
    mean = np.mean(values)
    variance = np.var(values)
    standard_deviation = np.sqrt(variance) + eps
    mean_absolute = np.mean(np.abs(values))
    rms = np.sqrt(np.mean(values**2))
    peak = np.max(np.abs(values))
    return np.asarray(
        [
            mean_absolute, rms, peak, mean, variance,
            np.mean(((values - mean) / standard_deviation) ** 3),
            np.mean(((values - mean) / standard_deviation) ** 4),
            rms / (mean_absolute + eps), peak / (rms + eps),
            peak / (mean_absolute + eps),
        ],
        dtype=np.float64,
    )


def extract_arc_features(values: np.ndarray, config: ArcFeatureConfig) -> np.ndarray:
    """Extract the same 24 features used by the standalone arc algorithm."""
    values = np.asarray(values, dtype=np.float64).reshape(-1)
    window_points = int(config.sample_rate * config.window_ms / 1000)
    if window_points <= 0 or values.size < window_points:
        raise ValueError("半波长度不足一个 1 ms 特征窗口。")
    windows = [values[i : i + window_points] for i in range(0, values.size, window_points)]
    time_features = np.mean(
        np.vstack([_time_features(window, config.eps) for window in windows]), axis=0
    )
    energies = []
    mean_absolutes = []
    for window in windows:
        coefficients = pywt.wavedec(window, config.wavelet, level=config.level)
        ordered = list(reversed(coefficients[1:])) + [coefficients[0]]
        energies.append([np.sum(coefficient**2) for coefficient in ordered])
        mean_absolutes.append([np.mean(np.abs(coefficient)) for coefficient in ordered])
    energy_sum = np.sum(np.asarray(energies), axis=0)
    mean_absolute = np.mean(np.asarray(mean_absolutes), axis=0)
    result = np.concatenate(
        [
            time_features,
            energy_sum / (energy_sum.sum() + config.eps),
            mean_absolute / (mean_absolute.sum() + config.eps),
        ]
    )
    if result.size != 24 or not np.all(np.isfinite(result)):
        raise ValueError("无法生成有效的24维电弧特征。")
    return result
