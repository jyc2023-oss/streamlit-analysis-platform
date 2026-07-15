from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import pywt
from scipy import signal

ALGORITHM_VERSION = "0.1.0"


@dataclass
class AnalysisOutput:
    title: str
    x: np.ndarray
    y: np.ndarray
    x_label: str
    y_label: str
    kind: str
    table: pd.DataFrame


def _finite(values: np.ndarray) -> np.ndarray:
    result = np.asarray(values, dtype=np.float64).reshape(-1)
    if result.size < 2:
        raise ValueError("分析区间至少需要两个采样点。")
    if not np.all(np.isfinite(result)):
        raise ValueError("数据中包含 NaN 或无穷值，请先清理数据。")
    return result


def waveform(values: np.ndarray, sample_rate: float, params: dict[str, Any]) -> AnalysisOutput:
    values = _finite(values)
    x = np.arange(values.size) / sample_rate
    table = pd.DataFrame(
        {
            "指标": ["采样点数", "最小值", "最大值", "均值", "标准差", "均方根"],
            "数值": [
                values.size,
                values.min(),
                values.max(),
                values.mean(),
                values.std(),
                np.sqrt(np.mean(values**2)),
            ],
        }
    )
    return AnalysisOutput("原始波形", x, values, "时间 (s)", "幅值", "line", table)


def fft_spectrum(values: np.ndarray, sample_rate: float, params: dict[str, Any]) -> AnalysisOutput:
    values = _finite(values)
    detrend = bool(params.get("detrend", True))
    if detrend:
        values = signal.detrend(values, type="constant")
    window = signal.windows.hann(values.size, sym=False)
    coherent_gain = window.mean()
    spectrum = np.fft.rfft(values * window)
    amplitude = 2.0 * np.abs(spectrum) / (values.size * coherent_gain)
    if amplitude.size:
        amplitude[0] /= 2.0
        if values.size % 2 == 0:
            amplitude[-1] /= 2.0
    frequencies = np.fft.rfftfreq(values.size, d=1.0 / sample_rate)
    min_frequency = max(0.0, float(params.get("min_frequency", 0.0)))
    max_frequency = min(sample_rate / 2, float(params.get("max_frequency", sample_rate / 2)))
    if min_frequency >= max_frequency:
        raise ValueError("FFT 最小频率必须小于最大频率。")
    mask = (frequencies >= min_frequency) & (frequencies <= max_frequency)
    visible_frequencies = frequencies[mask]
    visible_amplitude = amplitude[mask]
    if visible_amplitude.size == 0:
        raise ValueError("所选频率范围没有频点。")
    peak_index = int(np.argmax(visible_amplitude))
    table = pd.DataFrame(
        {
            "指标": ["频率分辨率 (Hz)", "峰值频率 (Hz)", "峰值幅值", "分析点数"],
            "数值": [
                sample_rate / values.size,
                visible_frequencies[peak_index],
                visible_amplitude[peak_index],
                values.size,
            ],
        }
    )
    return AnalysisOutput(
        "FFT 幅值谱", visible_frequencies, visible_amplitude, "频率 (Hz)", "幅值", "line", table
    )


def power_spectrum(
    values: np.ndarray, sample_rate: float, params: dict[str, Any]
) -> AnalysisOutput:
    values = _finite(values)
    segment_length = int(params.get("segment_length", min(4096, values.size)))
    segment_length = max(64, min(segment_length, values.size))
    frequencies, density = signal.welch(
        values,
        fs=sample_rate,
        window="hann",
        nperseg=segment_length,
        detrend="constant",
        scaling="density",
    )
    min_frequency = max(0.0, float(params.get("min_frequency", 0.0)))
    max_frequency = min(sample_rate / 2, float(params.get("max_frequency", sample_rate / 2)))
    if min_frequency >= max_frequency:
        raise ValueError("功率谱最小频率必须小于最大频率。")
    mask = (frequencies >= min_frequency) & (frequencies <= max_frequency)
    visible_frequencies = frequencies[mask]
    visible_density = density[mask]
    if visible_density.size == 0:
        raise ValueError("所选频率范围没有频点。")
    peak_index = int(np.argmax(visible_density))
    table = pd.DataFrame(
        {
            "指标": ["分段长度", "峰值频率 (Hz)", "峰值功率谱密度", "频点数"],
            "数值": [
                segment_length,
                visible_frequencies[peak_index],
                visible_density[peak_index],
                visible_density.size,
            ],
        }
    )
    return AnalysisOutput(
        "Welch 功率谱密度",
        visible_frequencies,
        visible_density,
        "频率 (Hz)",
        "功率谱密度",
        "line",
        table,
    )


def bandpass_filter(
    values: np.ndarray, sample_rate: float, params: dict[str, Any]
) -> AnalysisOutput:
    values = _finite(values)
    low = float(params.get("low_frequency", 10.0))
    high = float(params.get("high_frequency", sample_rate / 4))
    order = int(params.get("order", 4))
    nyquist = sample_rate / 2
    if not 0 < low < high < nyquist:
        raise ValueError(f"滤波频率必须满足 0 < 下限 < 上限 < {nyquist:g} Hz。")
    if not 1 <= order <= 12:
        raise ValueError("滤波器阶数必须在 1～12 之间。")
    sos = signal.butter(order, [low, high], btype="bandpass", fs=sample_rate, output="sos")
    minimum = 3 * (2 * len(sos) + 1)
    if values.size <= minimum:
        raise ValueError("分析区间过短，无法执行零相位滤波。")
    filtered = signal.sosfiltfilt(sos, values)
    x = np.arange(values.size) / sample_rate
    table = pd.DataFrame(
        {
            "指标": ["下限频率 (Hz)", "上限频率 (Hz)", "滤波器阶数", "滤波后均方根"],
            "数值": [low, high, order, np.sqrt(np.mean(filtered**2))],
        }
    )
    return AnalysisOutput("带通滤波结果", x, filtered, "时间 (s)", "幅值", "line", table)


def signal_envelope(
    values: np.ndarray, sample_rate: float, params: dict[str, Any]
) -> AnalysisOutput:
    values = _finite(values)
    envelope = np.abs(signal.hilbert(values))
    smooth_ms = float(params.get("smooth_ms", 1.0))
    window = max(1, int(round(sample_rate * smooth_ms / 1000)))
    if window > 1:
        kernel = np.ones(window, dtype=np.float64) / window
        envelope = np.convolve(envelope, kernel, mode="same")
    x = np.arange(values.size) / sample_rate
    table = pd.DataFrame(
        {
            "指标": ["平滑窗口 (ms)", "包络峰值", "包络均值", "包络均方根"],
            "数值": [
                smooth_ms,
                envelope.max(),
                envelope.mean(),
                np.sqrt(np.mean(envelope**2)),
            ],
        }
    )
    return AnalysisOutput("信号包络", x, envelope, "时间 (s)", "包络幅值", "line", table)


def wavelet_energy(
    values: np.ndarray, sample_rate: float, params: dict[str, Any]
) -> AnalysisOutput:
    values = _finite(values)
    wavelet = str(params.get("wavelet", "db3"))
    level = int(params.get("level", 5))
    if not 1 <= level <= 8:
        raise ValueError("小波分解层数必须在 1～8 之间。")
    try:
        packet = pywt.WaveletPacket(values, wavelet=wavelet, mode="symmetric", maxlevel=level)
    except Exception as exc:
        raise ValueError(f"无法使用小波 {wavelet}：{exc}") from exc
    nodes = packet.get_level(level, order="freq")
    energies = np.asarray([np.sum(np.square(node.data)) for node in nodes], dtype=np.float64)
    total = energies.sum()
    ratios = energies / total if total > 0 else np.zeros_like(energies)
    band_width = sample_rate / 2 / len(nodes)
    centers = (np.arange(len(nodes)) + 0.5) * band_width
    table = pd.DataFrame(
        {
            "频带序号": np.arange(1, len(nodes) + 1),
            "中心频率 (Hz)": centers,
            "能量": energies,
            "能量占比": ratios,
        }
    )
    return AnalysisOutput(
        f"小波包能量占比 ({wavelet}, level={level})",
        centers,
        ratios,
        "频带中心频率 (Hz)",
        "能量占比",
        "bar",
        table,
    )


ANALYSIS_TYPES: dict[str, dict[str, Any]] = {
    "waveform": {
        "label": "原始波形",
        "icon": "〰️",
        "description": "查看所选通道在时间域内的幅值变化。",
        "runner": waveform,
    },
    "fft": {
        "label": "FFT 幅值谱",
        "icon": "📶",
        "description": "分析信号中各频率分量的幅值。",
        "runner": fft_spectrum,
    },
    "power_spectrum": {
        "label": "Welch 功率谱",
        "icon": "📊",
        "description": "通过分段平均获得更稳定的功率谱密度。",
        "runner": power_spectrum,
    },
    "bandpass": {
        "label": "带通滤波",
        "icon": "🎚️",
        "description": "保留指定频率范围并观察滤波后波形。",
        "runner": bandpass_filter,
    },
    "envelope": {
        "label": "信号包络",
        "icon": "⌁",
        "description": "提取幅值包络，突出脉冲和调制变化。",
        "runner": signal_envelope,
    },
    "wavelet_energy": {
        "label": "小波包能量",
        "icon": "🧩",
        "description": "查看不同小波频带的相对能量。",
        "runner": wavelet_energy,
    },
}


def run_analysis(
    analysis_type: str,
    values: np.ndarray,
    sample_rate: float,
    parameters: dict[str, Any],
) -> AnalysisOutput:
    definition = ANALYSIS_TYPES.get(analysis_type)
    if definition is None:
        raise ValueError("未知分析类型。")
    if sample_rate <= 0:
        raise ValueError("采样率必须大于 0。")
    runner: Callable = definition["runner"]
    return runner(values, sample_rate, parameters)
