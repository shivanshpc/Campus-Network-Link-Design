"""Load and validate the CSV inputs for the campus link design."""

from pathlib import Path
from typing import Dict

import pandas as pd


REQUIRED_COLUMNS = {
    "links": [
        "link_id", "bldg_a", "bldg_b", "length_m", "target_mbps",
        "avail_target", "emi_heavy", "has_conduit",
    ],
    "media": [
        "media", "loss_db_per_km", "loss_db_per_100m", "bandwidth_mhz",
        "bandwidth_mhz_km", "carrier_mhz", "signal_levels", "pairs", "max_distance_m",
        "cost_per_m", "install_per_m", "fixed_cost", "mtbf_h", "mttr_h",
        "cable_failure_rate_per_km", "tx_power_dbm",
        "rx_sensitivity_dbm", "source",
    ],
    "params": [
        "budget", "budget_cut", "safety_factor", "noise_figure_db",
        "connector_loss_db", "min_margin_db", "crosstalk_noise_dbm",
        "emi_noise_dbm_normal", "emi_noise_dbm_heavy", "transceiver_mtbf_h",
        "transceiver_mttr_h", "armoured_surcharge_per_m", "source",
    ],
}


def _read_csv(data_dir: Path, name: str) -> pd.DataFrame:
    """Read one named input CSV, raising a clear error when it is absent."""
    path = data_dir / f"{name}.csv"
    if not path.is_file():
        raise FileNotFoundError(f"Missing input file: {path}")
    frame = pd.read_csv(path)
    missing = [column for column in REQUIRED_COLUMNS[name] if column not in frame]
    if missing:
        raise ValueError(f"{path} is missing required columns: {', '.join(missing)}")
    if frame.empty:
        raise ValueError(f"{path} must contain at least one data row")
    return frame


def _parse_bool(value: object, column: str, row_number: int) -> bool:
    """Convert common CSV boolean spellings and reject ambiguous values."""
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"true", "yes", "y", "1"}:
        return True
    if normalized in {"false", "no", "n", "0"}:
        return False
    raise ValueError(f"Invalid boolean {value!r} in {column}, row {row_number}")


def load_inputs(data_dir: str = "data") -> Dict[str, pd.DataFrame]:
    """Load links, media, and one-row parameters from ``data_dir``."""
    directory = Path(data_dir)
    inputs = {name: _read_csv(directory, name) for name in REQUIRED_COLUMNS}
    links = inputs["links"].copy()
    links["emi_heavy"] = [
        _parse_bool(value, "emi_heavy", index + 2)
        for index, value in enumerate(links["emi_heavy"])
    ]
    links["has_conduit"] = [
        _parse_bool(value, "has_conduit", index + 2)
        for index, value in enumerate(links["has_conduit"])
    ]
    params = inputs["params"].copy()
    if len(params) != 1:
        raise ValueError("data/params.csv must contain exactly one data row")
    numeric_link_columns = set(REQUIRED_COLUMNS["links"]) - {
        "link_id", "bldg_a", "bldg_b", "emi_heavy", "has_conduit",
    }
    for column in numeric_link_columns:
        links[column] = pd.to_numeric(links[column], errors="raise")
    for column in set(REQUIRED_COLUMNS["media"]) - {"media", "source"}:
        inputs["media"][column] = pd.to_numeric(inputs["media"][column], errors="raise")
    for column in set(REQUIRED_COLUMNS["params"]) - {"source"}:
        params[column] = pd.to_numeric(params[column], errors="raise")
    inputs["links"] = links
    inputs["params"] = params
    return inputs


if __name__ == "__main__":
    loaded = load_inputs()
    print("Loaded: " + ", ".join(f"{name}={len(frame)}" for name, frame in loaded.items()))