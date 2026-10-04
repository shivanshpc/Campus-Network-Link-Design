"""Line-code selection, encoding, and spectrum generation."""

from pathlib import Path
from typing import Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


DEFAULT_SEED = 2026
SAMPLES_PER_BIT = 16
SPECTRUM_STREAMS = 200
SPECTRUM_BITS = 1024
BITS_PER_SYMBOL = 8
FOUR_B_FIVE_B_FACTOR = 5.0 / 4.0
EIGHT_B_TEN_B_FACTOR = 10.0 / 8.0
SIXTY_FOUR_B_SIXTY_SIX_B_FACTOR = 66.0 / 64.0


def choose_line_code(channel_bandwidth: float, data_rate: float) -> Tuple[str, str]:
    """Choose the lowest-bandwidth synchronized code that fits ``B >= required_rate``."""
    if channel_bandwidth >= data_rate:
        return "Manchester", "Manchester fits the channel and guarantees a transition per bit."
    if channel_bandwidth >= data_rate * SIXTY_FOUR_B_SIXTY_SIX_B_FACTOR:
        return "64B/66B", "64B/66B adds low overhead while bounding run length for clock recovery."
    if channel_bandwidth >= data_rate * FOUR_B_FIVE_B_FACTOR:
        return "4B/5B", "4B/5B limits runs and needs less bandwidth than a self-clocking Manchester signal."
    if channel_bandwidth >= data_rate * EIGHT_B_TEN_B_FACTOR:
        return "8B/10B", "8B/10B limits runs and maintains DC balance with moderate overhead."
    return "64B/66B", "No synchronized code fits the channel; 64B/66B is retained as the lowest-overhead block-code choice and rate validation will reject it."


def encode_nrz(bits: np.ndarray, samples_per_bit: int = SAMPLES_PER_BIT) -> np.ndarray:
    """Encode bits as levels using ``0 -> -1`` and ``1 -> +1`` for each sample."""
    return np.repeat(np.where(bits == 0, -1.0, 1.0), samples_per_bit)


def encode_rz(bits: np.ndarray, samples_per_bit: int = SAMPLES_PER_BIT) -> np.ndarray:
    """Encode RZ using ``level = bit_level for first half, then zero``."""
    levels = np.where(bits == 0, -1.0, 1.0)
    half = samples_per_bit // 2
    signal = np.repeat(levels, samples_per_bit).reshape(len(levels), samples_per_bit)
    signal[:, half:] = 0.0
    return signal.ravel()


def encode_manchester(bits: np.ndarray, samples_per_bit: int = SAMPLES_PER_BIT) -> np.ndarray:
    """Encode Manchester using ``0 -> (+1, -1)`` and ``1 -> (-1, +1)``."""
    levels = np.where(bits == 0, 1.0, -1.0)
    half = samples_per_bit // 2
    signal = np.empty((len(levels), samples_per_bit))
    signal[:, :half] = levels[:, None]
    signal[:, half:] = -levels[:, None]
    return signal.ravel()


def _spectrum(signal: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Return positive FFT frequencies and power for ``P = abs(FFT(x))^2``."""
    frequencies = np.fft.rfftfreq(len(signal), d=1.0)
    power = np.abs(np.fft.rfft(signal)) ** 2 / len(signal)
    return frequencies, power


def averaged_power_spectrum(
    code: str,
    seed: int = DEFAULT_SEED,
    streams: int = SPECTRUM_STREAMS,
    bits_per_stream: int = SPECTRUM_BITS,
    samples_per_bit: int = SAMPLES_PER_BIT,
) -> Tuple[np.ndarray, np.ndarray]:
    """Average oversampled power spectra with frequency measured as ``f/R``."""
    encoders = {
        "NRZ": encode_nrz,
        "RZ": encode_rz,
        "Manchester": encode_manchester,
    }
    if code not in encoders:
        raise ValueError(f"Unsupported spectrum code: {code}")
    rng = np.random.default_rng(seed)
    powers = []
    frequencies = None
    for _ in range(streams):
        bits = rng.integers(0, 2, size=bits_per_stream)
        signal = encoders[code](bits, samples_per_bit)
        frequencies, power = _spectrum(signal)
        powers.append(power)
    assert frequencies is not None
    return frequencies * samples_per_bit, np.mean(powers, axis=0)


def spectrum_bandwidth_90(
    code: str,
    seed: int = DEFAULT_SEED,
    streams: int = SPECTRUM_STREAMS,
    bits_per_stream: int = SPECTRUM_BITS,
    samples_per_bit: int = SAMPLES_PER_BIT,
) -> float:
    """Return the frequency in ``f/R`` containing 90% of positive PSD power."""
    frequencies, power = averaged_power_spectrum(code, seed, streams, bits_per_stream, samples_per_bit)
    cumulative = np.cumsum(power)
    return float(frequencies[np.searchsorted(cumulative, cumulative[-1] * 0.90)])


def save_spectrum_plot(output_path: str = "results/line_code_spectrum.png", seed: int = DEFAULT_SEED) -> None:
    """Create an averaged, fixed-seed comparison plot in ``f/R`` and dB."""
    spectra = {name: averaged_power_spectrum(name, seed) for name in ("NRZ", "RZ", "Manchester")}
    peak = max(float(np.max(power)) for _, power in spectra.values())
    figure, axis = plt.subplots(figsize=(10, 6), constrained_layout=True)
    curve_colors = {"NRZ": "tab:blue", "RZ": "tab:orange", "Manchester": "tab:green"}
    bandwidths = {}
    for name, (frequencies, power) in spectra.items():
        visible = frequencies <= 2.0
        power_db = 10.0 * np.log10(np.maximum(power, peak * 1e-12) / peak)
        color = curve_colors[name]
        axis.plot(frequencies[visible], power_db[visible], color=color, linewidth=1.0, label=name)
        bandwidths[name] = spectrum_bandwidth_90(name, seed=seed)
    marker_frequencies = {"NRZ": 1.0, "RZ": 2.0, "Manchester": 1.0}
    for name, frequency in marker_frequencies.items():
        axis.axvline(
            frequency,
            color=curve_colors[name],
            linestyle="--",
            linewidth=0.8,
            alpha=0.75,
            label=f"{name} edge/null ({frequency:g} f/R)",
        )
    bandwidth_text = "90% power bandwidth: " + ", ".join(
        f"{name}={value:.3f} f/R" for name, value in bandwidths.items()
    )
    axis.text(
        0.99,
        0.03,
        bandwidth_text,
        transform=axis.transAxes,
        ha="right",
        va="bottom",
        fontsize=8,
        bbox={"facecolor": "white", "alpha": 0.8, "edgecolor": "none"},
    )
    axis.set_xlim(0.0, 2.0)
    axis.set_ylim(-80.0, 2.0)
    axis.set_xlabel("Normalized frequency, f/R")
    axis.set_ylabel("Power spectral density (dB, normalized)")
    axis.set_title("Averaged line-code power spectra")
    axis.grid(True, alpha=0.25)
    axis.legend()
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=150)
    plt.close(figure)


def apply_line_codes(options: pd.DataFrame, params: pd.DataFrame) -> pd.DataFrame:
    """Add ``line_code`` and ``line_code_reason`` using the safety-adjusted rate."""
    if len(params) != 1:
        raise ValueError("params must contain exactly one row")
    safety_factor = float(params.iloc[0]["safety_factor"])
    result = options.copy()
    choices = [
        choose_line_code(float(row["bandwidth_mhz"] if row["media"] == "cat6" else (
            row["bandwidth_mhz_km"] / (row["length_m"] / 1000.0) if row["media"] in {"om3", "smf"} else row["bandwidth_mhz"]
        )), float(row["target_mbps"]) * safety_factor)
        for _, row in result.iterrows()
    ]
    result["line_code"] = [choice[0] for choice in choices]
    result["line_code_reason"] = [choice[1] for choice in choices]
    return result