import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parents[1] / "code"))

from linecode import averaged_power_spectrum, encode_manchester, encode_nrz, encode_rz, spectrum_bandwidth_90


def test_line_codes_are_oversampled() -> None:
    bits = np.array([0, 1, 0, 1])
    assert len(encode_nrz(bits)) == 64
    assert len(encode_rz(bits)) == 64
    assert len(encode_manchester(bits)) == 64


def test_measured_bandwidth_order_and_manchester_low_frequency_null() -> None:
    bandwidths = {
        code: spectrum_bandwidth_90(code, streams=40, bits_per_stream=512)
        for code in ("NRZ", "RZ", "Manchester")
    }
    assert bandwidths["NRZ"] < bandwidths["RZ"] < bandwidths["Manchester"]
    frequencies, power = averaged_power_spectrum("Manchester", streams=40, bits_per_stream=512)
    low_frequency_power = float(power[np.argmin(np.abs(frequencies - 0.05))])
    peak_power = float(np.max(power))
    assert low_frequency_power / peak_power < 0.01