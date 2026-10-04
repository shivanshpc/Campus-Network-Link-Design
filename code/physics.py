"""Physical-layer calculations for every link and medium combination."""

import math
from typing import Dict

import numpy as np
import pandas as pd


METERS_PER_KM = 1000.0
METERS_PER_HUNDRED = 100.0
MHZ_TO_HZ = 1_000_000.0
DBM_REFERENCE_MW = 1.0
FREE_SPACE_CONSTANT_DB = 32.44
def db_to_mw(dbm: float) -> float:
    """Convert dBm to mW using ``mW = 10 ** (dBm / 10)``."""
    return 10.0 ** (dbm / 10.0) * DBM_REFERENCE_MW


def mw_to_dbm(mw: float) -> float:
    """Convert mW to dBm using ``dBm = 10 * log10(mW)``."""
    if mw <= 0:
        raise ValueError("Power/noise in mW must be positive")
    return 10.0 * math.log10(mw / DBM_REFERENCE_MW)


def copper_loss(loss_db_per_100m: float, length_m: float) -> float:
    """Calculate copper loss using ``loss = loss_per_100m * length_m / 100``."""
    return loss_db_per_100m * length_m / METERS_PER_HUNDRED


def free_space_loss(length_km: float, carrier_mhz: float) -> float:
    """Calculate free-space loss using ``20log10(km) + 20log10(MHz) + 32.44``."""
    return 20.0 * math.log10(length_km) + 20.0 * math.log10(carrier_mhz) + FREE_SPACE_CONSTANT_DB


def thermal_noise_dbm(bandwidth_hz: float, noise_figure_db: float) -> float:
    """Calculate thermal noise using ``-174 + 10log10(B_hz) + noise_figure``."""
    return -174.0 + 10.0 * math.log10(bandwidth_hz) + noise_figure_db


def total_noise_dbm(thermal_dbm: float, crosstalk_dbm: float, emi_dbm: float) -> float:
    """Sum noise powers using ``10log10(sum(10 ** (noise_dBm / 10)))``."""
    return mw_to_dbm(sum(db_to_mw(value) for value in (thermal_dbm, crosstalk_dbm, emi_dbm)))


def shannon_mbps(bandwidth_mhz: float, snr_db: float, pairs: int) -> float:
    """Calculate total Shannon capacity using ``C = pairs * B * log2(1 + SNR_ratio)``."""
    return pairs * bandwidth_mhz * math.log2(1.0 + 10.0 ** (snr_db / 10.0))


def nyquist_mbps(bandwidth_mhz: float, signal_levels: int, pairs: int) -> float:
    """Calculate total Nyquist capacity using ``C = pairs * 2 * B * log2(M)``."""
    return pairs * 2.0 * bandwidth_mhz * math.log2(signal_levels)


def _evaluate_row(link: pd.Series, medium: pd.Series, params: pd.Series) -> Dict[str, object]:
    """Evaluate one link-medium pair using the CSV-provided physical parameters."""
    media_name = medium["media"]
    length_m = float(link["length_m"])
    length_km = length_m / METERS_PER_KM
    distance_ok = length_m <= float(medium["max_distance_m"])
    connector_loss = float(params["connector_loss_db"])
    if media_name == "cat6":
        loss_db = copper_loss(float(medium["loss_db_per_100m"]), length_m)
        rx_power = float(medium["tx_power_dbm"]) - loss_db - connector_loss
        pass_power = distance_ok
        bandwidth = float(medium["bandwidth_mhz"])
    elif media_name in {"om3", "smf"}:
        loss_db = float(medium["loss_db_per_km"]) * length_km
        rx_power = float(medium["tx_power_dbm"]) - loss_db - connector_loss
        margin_db = rx_power - float(medium["rx_sensitivity_dbm"])
        pass_power = distance_ok and margin_db >= float(params["min_margin_db"])
        bandwidth = float(medium["bandwidth_mhz_km"]) / length_km
    elif media_name == "radio":
        loss_db = free_space_loss(length_km, float(medium["carrier_mhz"]))
        rx_power = float(medium["tx_power_dbm"]) - loss_db - connector_loss
        margin_db = rx_power - float(medium["rx_sensitivity_dbm"])
        pass_power = distance_ok and margin_db >= float(params["min_margin_db"])
        bandwidth = float(medium["bandwidth_mhz"])
    else:
        raise ValueError(f"Unsupported medium: {media_name}")
    margin_db = float("nan") if media_name == "cat6" else rx_power - float(medium["rx_sensitivity_dbm"])
    thermal = thermal_noise_dbm(bandwidth * MHZ_TO_HZ, float(params["noise_figure_db"]))
    emi = float(params["emi_noise_dbm_heavy"] if link["emi_heavy"] else params["emi_noise_dbm_normal"])
    noise = total_noise_dbm(thermal, float(params["crosstalk_noise_dbm"]), emi)
    snr = rx_power - noise
    signal_levels = int(medium["signal_levels"])
    pairs = int(medium["pairs"])
    shannon = shannon_mbps(bandwidth, snr, pairs)
    nyquist = nyquist_mbps(bandwidth, signal_levels, pairs)
    target_rate = float(link["target_mbps"]) * float(params["safety_factor"])
    required_snr_db = 10.0 * math.log10(
        2.0 ** (target_rate / (pairs * bandwidth)) - 1.0
    )
    pass_snr = True if media_name in {"om3", "smf"} else snr >= required_snr_db
    pass_rate = target_rate <= min(shannon, nyquist)
    if media_name in {"om3", "smf"}:
        snr_output = float("nan")
    else:
        snr_output = snr
        pass_rate = pass_rate and distance_ok
    return {
        **link.to_dict(), **medium.to_dict(), "loss_db": loss_db,
        "rx_power_dbm": rx_power, "margin_db": margin_db, "pass_power": pass_power,
        "noise_dbm": noise, "snr_db": snr_output, "shannon_mbps": shannon,
        "nyquist_mbps": nyquist, "pass_snr": pass_snr, "pass_rate": pass_rate,
        "armoured_surcharge_per_m": float(params["armoured_surcharge_per_m"]),
        "safety_factor": float(params["safety_factor"]),
        "min_margin_db": float(params["min_margin_db"]),
        "required_snr_db": required_snr_db,
    }


def evaluate_options(links: pd.DataFrame, media: pd.DataFrame, params: pd.DataFrame) -> pd.DataFrame:
    """Return one physical evaluation row for every Cartesian link-medium pair."""
    if len(params) != 1:
        raise ValueError("params must contain exactly one row")
    rows = [_evaluate_row(link, medium, params.iloc[0]) for _, link in links.iterrows() for _, medium in media.iterrows()]
    return pd.DataFrame(rows)