from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import pywt
from scipy.signal import butter, sosfiltfilt

MAINS_FREQUENCY_HZ = 50.0
WAVELET_NAME = "bior3.1"
CHANNEL_LABELS_8 = ["5m", "10m", "20m", "40m", "80m", "120m", "160m", "背景支路"]
CHANNEL_LABELS_2 = ["电弧发生处", "2m主干"]
CHANNEL_COLORS = [
    "#1f77b4",
    "#ff7f0e",
    "#2ca02c",
    "#d62728",
    "#9467bd",
    "#8c564b",
    "#e377c2",
    "#7f7f7f",
    "#17becf",
    "#bcbd22",
]


@dataclass
class PairedChannelCycles:
    label: str
    group: str
    channel: str
    noarc_cycles: list[np.ndarray]
    arc_cycles: list[np.ndarray]


@dataclass
class PairedPanel:
    label: str
    x: np.ndarray
    noarc: np.ndarray
    arc: np.ndarray


@dataclass
class PairedAnalysisOutput:
    title: str
    kind: str
    panels: list[PairedPanel]
    x_label: str
    y_label: str
    table: pd.DataFrame


PAIRED_ANALYSIS_TYPES: dict[str, dict[str, Any]] = {
    "paired_normalized_fft": {
        "label": "10通道 · 50Hz归一化FFT",
        "icon": "📊",
        "description": "选择无弧和有弧各 2 个周波，绘制原脚本的十通道归一化 FFT 对比图。",
        "cycle_counts": (2,),
    },
    "paired_absolute_fft": {
        "label": "10通道 · 滤波FFT对比",
        "icon": "🔬",
        "description": "选择无弧和有弧各 5 或 10 个周波，绘制可设滤波范围的绝对 FFT。",
        "cycle_counts": (5, 10),
    },
    "paired_wpt_ratio": {
        "label": "10通道 · 小波能量比",
        "icon": "🧩",
        "description": "选择无弧和有弧各 5 或 10 个周波，计算 bior3.1 小波包有弧/无弧能量比。",
        "cycle_counts": (5, 10),
    },
    "paired_fft_band_power": {
        "label": "10通道 · 128频带功率",
        "icon": "⚡",
        "description": "选择无弧和有弧各 5 个周波，绘制两个同步的 128 频带绝对功率面板。",
        "cycle_counts": (5,),
    },
}


def detect_cycle_starts(values: np.ndarray, sample_rate: float, usable_samples: int) -> np.ndarray:
    """按原脚本规则检测 50 Hz 正向过零点，不足时退回均匀周波网格。"""
    points_per_cycle = int(round(sample_rate / MAINS_FREQUENCY_HZ))
    if points_per_cycle < 2:
        raise ValueError("采样率过低，无法按 50 Hz 划分周波。")
    usable_samples = min(int(usable_samples), len(values))
    decimation = max(1, points_per_cycle // 500)
    sampled = np.array(values[:usable_samples:decimation], dtype=np.float64, copy=True)
    if sampled.size < 2:
        return np.empty(0, dtype=np.int64)
    sampled -= np.median(sampled)
    crossing_small = np.flatnonzero((sampled[:-1] <= 0) & (sampled[1:] > 0)) + 1
    crossings = crossing_small.astype(np.int64) * decimation

    accepted: list[int] = []
    min_gap = int(points_per_cycle * 0.70)
    max_gap = int(points_per_cycle * 1.30)
    for item in crossings:
        crossing = int(item)
        if crossing + points_per_cycle > usable_samples:
            continue
        if not accepted or crossing - accepted[-1] >= min_gap:
            if accepted and crossing - accepted[-1] > max_gap:
                missing = int(round((crossing - accepted[-1]) / points_per_cycle)) - 1
                for _ in range(missing):
                    candidate = accepted[-1] + points_per_cycle
                    if candidate + points_per_cycle <= usable_samples:
                        accepted.append(candidate)
            accepted.append(crossing)

    if len(accepted) < 2:
        return np.arange(
            0,
            usable_samples - points_per_cycle + 1,
            points_per_cycle,
            dtype=np.int64,
        )
    return np.asarray(sorted(set(accepted)), dtype=np.int64)


def normalized_fft(cycles: list[np.ndarray], sample_rate: float) -> tuple[np.ndarray, np.ndarray]:
    segment = np.concatenate(cycles)
    window = np.hanning(len(segment))
    frequencies = np.fft.rfftfreq(len(segment), d=1.0 / sample_rate)
    amplitude = np.abs(np.fft.rfft(segment * window))
    index_50hz = int(np.argmin(np.abs(frequencies - MAINS_FREQUENCY_HZ)))
    if amplitude[index_50hz] > 1e-12:
        amplitude = amplitude / amplitude[index_50hz]
    return frequencies, 20.0 * np.log10(amplitude + 1e-12)


def filter_cycles(
    cycles: list[np.ndarray], sample_rate: float, low: float, high: float
) -> list[np.ndarray]:
    nyquist = sample_rate / 2.0
    tolerance = max(1e-9, nyquist * 1e-12)
    if not 0 <= low < high <= nyquist:
        raise ValueError(f"滤波范围必须满足 0 ≤ 下限 < 上限 ≤ {nyquist:g} Hz。")
    if low <= tolerance and high >= nyquist - tolerance:
        return cycles
    if low <= tolerance:
        sos = butter(6, high / nyquist, btype="lowpass", output="sos")
    elif high >= nyquist - tolerance:
        sos = butter(6, low / nyquist, btype="highpass", output="sos")
    else:
        sos = butter(6, [low / nyquist, high / nyquist], btype="bandpass", output="sos")
    return [sosfiltfilt(sos, cycle) for cycle in cycles]


def absolute_fft(
    cycles: list[np.ndarray], sample_rate: float, low: float, high: float
) -> tuple[np.ndarray, np.ndarray]:
    segment = np.concatenate(filter_cycles(cycles, sample_rate, low, high))
    window = np.hanning(len(segment))
    coherent_gain = np.sum(window)
    amplitude = 2.0 * np.abs(np.fft.rfft(segment * window)) / max(coherent_gain, 1e-12)
    if len(amplitude):
        amplitude[0] *= 0.5
        if len(segment) % 2 == 0:
            amplitude[-1] *= 0.5
    frequencies = np.fft.rfftfreq(len(segment), d=1.0 / sample_rate)
    return frequencies, 20.0 * np.log10(amplitude + 1e-12)


def wpt_energy(cycles: list[np.ndarray], bands: int) -> np.ndarray:
    if bands not in {32, 64, 128}:
        raise ValueError("小波包频带数量只能是 32、64 或 128。")
    level = int(np.log2(bands))
    per_cycle = []
    for cycle in cycles:
        packet = pywt.WaveletPacket(
            data=cycle, wavelet=WAVELET_NAME, mode="periodization", maxlevel=level
        )
        nodes = packet.get_level(level, order="freq")
        per_cycle.append(np.asarray([np.sum(node.data**2) for node in nodes], dtype=np.float64))
    return np.mean(np.stack(per_cycle, axis=0), axis=0)


def fft_band_power_128(
    cycles: list[np.ndarray], sample_rate: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    bands = 128
    band_edges = np.linspace(0.0, sample_rate / 2.0, bands + 1)
    per_cycle = []
    for cycle in cycles:
        values = np.asarray(cycle, dtype=np.float64).copy()
        values -= np.mean(values)
        window = np.hanning(len(values))
        spectrum = np.fft.rfft(values * window)
        psd = np.abs(spectrum) ** 2 / max(sample_rate * float(np.sum(window**2)), 1e-300)
        if len(values) % 2 == 0:
            psd[1:-1] *= 2.0
        else:
            psd[1:] *= 2.0
        frequencies = np.fft.rfftfreq(len(values), d=1.0 / sample_rate)
        df = sample_rate / len(values)
        power, _ = np.histogram(frequencies, bins=band_edges, weights=psd * df)
        per_cycle.append(power.astype(np.float64, copy=False))
    mean_power = np.mean(np.stack(per_cycle, axis=0), axis=0)
    centers = (band_edges[:-1] + band_edges[1:]) / 2.0
    return band_edges, centers, mean_power


def _validate_channels(channels: list[PairedChannelCycles]) -> None:
    if len(channels) != 10:
        raise ValueError("配对分析需要一个 8 通道文件和一个 2 通道文件，共 10 个通道。")
    for item in channels:
        if not item.noarc_cycles or not item.arc_cycles:
            raise ValueError(f"{item.label} 缺少无弧或有弧周波。")


def _wide_table(panels: list[PairedPanel], x_name: str) -> pd.DataFrame:
    table: dict[str, np.ndarray] = {x_name: panels[0].x}
    for panel in panels:
        table[f"无弧_{panel.label}"] = panel.noarc
        table[f"有弧_{panel.label}"] = panel.arc
    return pd.DataFrame(table)


def run_paired_analysis(
    analysis_type: str,
    channels: list[PairedChannelCycles],
    sample_rate: float,
    parameters: dict[str, Any],
) -> PairedAnalysisOutput:
    _validate_channels(channels)
    if analysis_type not in PAIRED_ANALYSIS_TYPES:
        raise ValueError("未知的配对分析类型。")

    panels: list[PairedPanel] = []
    if analysis_type == "paired_normalized_fft":
        for item in channels:
            noarc_x, noarc_y = normalized_fft(item.noarc_cycles, sample_rate)
            arc_x, arc_y = normalized_fft(item.arc_cycles, sample_rate)
            panels.append(PairedPanel(item.label, noarc_x[1:], noarc_y[1:], arc_y[1:]))
        return PairedAnalysisOutput(
            "50 Hz归一化FFT：无弧 vs 有弧",
            analysis_type,
            panels,
            "频率 (Hz)",
            "归一化幅值 (dB)",
            _wide_table(panels, "频率_Hz"),
        )

    if analysis_type == "paired_absolute_fft":
        low = float(parameters.get("low_frequency", 0.0))
        high = float(parameters.get("high_frequency", sample_rate / 2.0))
        for item in channels:
            noarc_x, noarc_y = absolute_fft(item.noarc_cycles, sample_rate, low, high)
            arc_x, arc_y = absolute_fft(item.arc_cycles, sample_rate, low, high)
            mask = (noarc_x >= low) & (noarc_x <= high)
            panels.append(PairedPanel(item.label, noarc_x[mask], noarc_y[mask], arc_y[mask]))
        return PairedAnalysisOutput(
            f"非归一化FFT：无弧 vs 有弧｜滤波 {low:g}–{high:g} Hz",
            analysis_type,
            panels,
            "频率 (Hz)",
            "幅值 (dB re 1 unit)",
            _wide_table(panels, "频率_Hz"),
        )

    if analysis_type == "paired_wpt_ratio":
        bands = int(parameters.get("bands", 128))
        x = np.arange(1, bands + 1)
        reference_2ch = next(
            (item for item in channels if item.group == "2CH" and item.channel == "CH02"),
            None,
        )
        table: dict[str, np.ndarray] = {"频带编号": x}
        for item in channels:
            noarc_cycles = (
                reference_2ch.noarc_cycles
                if item.group == "2CH" and reference_2ch is not None
                else item.noarc_cycles
            )
            no_energy = wpt_energy(noarc_cycles, bands)
            arc_energy = wpt_energy(item.arc_cycles, bands)
            epsilon = max(float(np.max(no_energy)) * 1e-12, 1e-18)
            ratio = 10.0 * np.log10(np.maximum(arc_energy / (no_energy + epsilon), 1e-12))
            panels.append(PairedPanel(item.label, x, np.empty(0), ratio))
            suffix = "_对无弧CH02" if item.group == "2CH" else ""
            table[f"{item.label}{suffix}_能量比dB"] = ratio
        return PairedAnalysisOutput(
            f"{WAVELET_NAME}小波包有弧/无弧能量比｜{bands}频带",
            analysis_type,
            panels,
            "小波包频带编号",
            "有弧能量 / 无弧能量 (dB)",
            pd.DataFrame(table),
        )

    table = {"频带编号": np.arange(1, 129)}
    edges: np.ndarray | None = None
    centers: np.ndarray | None = None
    for item in channels:
        edges, centers, noarc_power = fft_band_power_128(item.noarc_cycles, sample_rate)
        _, _, arc_power = fft_band_power_128(item.arc_cycles, sample_rate)
        noarc_db = 10.0 * np.log10(np.maximum(noarc_power, 1e-300))
        arc_db = 10.0 * np.log10(np.maximum(arc_power, 1e-300))
        panels.append(PairedPanel(item.label, np.arange(1, 129), noarc_db, arc_db))
        table[f"有弧_{item.label}_频带功率dB"] = arc_db
        table[f"无弧_{item.label}_频带功率dB"] = noarc_db
    assert edges is not None and centers is not None
    table["频带下限_Hz"] = edges[:-1]
    table["频带上限_Hz"] = edges[1:]
    table["中心频率_Hz"] = centers
    return PairedAnalysisOutput(
        "FFT绝对频带功率：有弧 vs 无弧｜各5周波｜128频带",
        analysis_type,
        panels,
        "FFT积分频带编号",
        "绝对频带功率 (dB re 1 unit²)",
        pd.DataFrame(table),
    )
