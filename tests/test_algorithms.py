import numpy as np

from src.analysis.arc_features import ArcFeatureConfig, extract_arc_features
from src.analysis.paired import (
    PairedChannelCycles,
    detect_cycle_starts,
    fft_band_power_128,
    run_paired_analysis,
)
from src.analysis.registry import (
    bandpass_filter,
    fft_spectrum,
    power_spectrum,
    signal_envelope,
    waveform,
    wavelet_energy,
)
from src.components.plots import build_paired_figure


def test_waveform_metrics() -> None:
    output = waveform(np.array([1.0, -1.0, 1.0, -1.0]), 4.0, {})
    assert output.kind == "line"
    assert len(output.x) == 4
    assert "均方根" in output.table["指标"].tolist()


def test_fft_finds_tone() -> None:
    sample_rate = 4096.0
    time = np.arange(4096) / sample_rate
    values = np.sin(2 * np.pi * 256 * time)
    output = fft_spectrum(values, sample_rate, {"min_frequency": 0, "max_frequency": 1000})
    peak_frequency = output.x[int(np.argmax(output.y))]
    assert abs(peak_frequency - 256) <= 1


def test_bandpass_reduces_out_of_band_tone() -> None:
    sample_rate = 4000.0
    time = np.arange(8000) / sample_rate
    values = np.sin(2 * np.pi * 100 * time) + np.sin(2 * np.pi * 1000 * time)
    output = bandpass_filter(
        values,
        sample_rate,
        {"low_frequency": 80, "high_frequency": 120, "order": 4},
    )
    assert np.sqrt(np.mean(output.y**2)) < np.sqrt(np.mean(values**2))
    assert np.sqrt(np.mean(output.y**2)) > 0.5


def test_wavelet_energy_ratios_sum_to_one() -> None:
    values = np.sin(np.linspace(0, 20 * np.pi, 4096))
    output = wavelet_energy(values, 4096.0, {"wavelet": "db3", "level": 4})
    assert output.kind == "bar"
    assert np.isclose(output.y.sum(), 1.0)


def test_power_spectrum_finds_tone() -> None:
    sample_rate = 4096.0
    time = np.arange(8192) / sample_rate
    values = np.sin(2 * np.pi * 300 * time)
    output = power_spectrum(values, sample_rate, {"segment_length": 4096})
    assert abs(output.x[int(np.argmax(output.y))] - 300) <= 1


def test_signal_envelope_is_positive() -> None:
    time = np.arange(4096) / 4096
    values = (1 + 0.5 * np.sin(2 * np.pi * 5 * time)) * np.sin(2 * np.pi * 300 * time)
    output = signal_envelope(values, 4096, {"smooth_ms": 1.0})
    assert np.all(output.y >= 0)
    assert output.y.max() > output.y.min()


def test_waveform_downsampling_preserves_full_duration_and_extrema() -> None:
    values = np.zeros(100_000)
    values[12_345] = 20
    values[88_888] = -15
    output = waveform(values, 10_000, {"max_output_points": 2_000})
    assert len(output.x) <= 2_000
    assert output.y.max() == 20
    assert output.y.min() == -15
    assert output.x[-1] > 9.9


def test_cycle_detection_finds_50hz_cycles() -> None:
    sample_rate = 10_000
    time = np.arange(sample_rate) / sample_rate
    values = np.sin(2 * np.pi * 50 * time)
    starts = detect_cycle_starts(values, sample_rate, len(values))
    assert len(starts) >= 48
    assert np.allclose(np.diff(starts), sample_rate / 50, atol=2)


def test_paired_normalized_fft_builds_ten_panels() -> None:
    sample_rate = 10_000
    time = np.arange(200) / sample_rate
    channels = []
    for index in range(10):
        noarc = [np.sin(2 * np.pi * 50 * time) for _ in range(2)]
        arc = [
            np.sin(2 * np.pi * 50 * time) + 0.1 * np.sin(2 * np.pi * 500 * time) for _ in range(2)
        ]
        channels.append(
            PairedChannelCycles(
                label=f"CH{index + 1}",
                group="8CH" if index < 8 else "2CH",
                channel=f"CH{index % 8 + 1:02d}" if index < 8 else f"CH{index - 7:02d}",
                noarc_cycles=noarc,
                arc_cycles=arc,
            )
        )
    output = run_paired_analysis("paired_normalized_fft", channels, sample_rate, {})
    assert len(output.panels) == 10
    assert "频率_Hz" in output.table
    figure = build_paired_figure(output)
    assert len(figure.data) == 20


def test_fft_band_power_has_128_bands() -> None:
    sample_rate = 12_800
    time = np.arange(256) / sample_rate
    edges, centers, power = fft_band_power_128([np.sin(2 * np.pi * 1000 * time)], sample_rate)
    assert len(edges) == 129
    assert len(centers) == len(power) == 128
    assert np.all(power >= 0)
def test_arc_feature_extractor_returns_finite_24_dimensions() -> None:
    time = np.arange(20_000, dtype=np.float64) / 2_000_000
    half_wave = np.sin(2 * np.pi * 50 * time) + 0.02 * np.sin(2 * np.pi * 20_000 * time)
    features = extract_arc_features(half_wave, ArcFeatureConfig(sample_rate=2_000_000))
    assert features.shape == (24,)
    assert np.isfinite(features).all()
    np.testing.assert_allclose(features[10:17].sum(), 1.0, rtol=1e-10)
    np.testing.assert_allclose(features[17:24].sum(), 1.0, rtol=1e-10)
