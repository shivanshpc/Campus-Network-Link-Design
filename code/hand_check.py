"""Generate spreadsheet hand-check material for two representative links."""

from pathlib import Path
import math
from typing import Dict, List

import pandas as pd

from load import load_inputs
from physics import db_to_mw, mw_to_dbm, shannon_mbps, nyquist_mbps, thermal_noise_dbm
from reliability import availability, link_availability, parallel_availability
from selection import option_cost
from physics import evaluate_options
from linecode import apply_line_codes
from reliability import evaluate_availability


ROOT = Path(__file__).parents[1]
RESULTS = ROOT / "results"


def _value(value: object) -> str:
    """Format a value at full precision for the generated markdown."""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    return str(value)


def _rounded(value: object) -> str:
    """Format a readable rounded companion value."""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return f"{float(value):.6g}"
    return str(value)


def _row(rows: List[Dict[str, str]], step: str, formula: str, unit: str, value: object) -> None:
    """Append one calculation row with intentionally blank spreadsheet columns."""
    rows.append({
        "step": step,
        "formula": formula,
        "unit": unit,
        "project computed value": _value(value),
        "rounded display value": _rounded(value),
        "my spreadsheet value": "",
        "match?": "",
    })


def _inputs_section(title: str, values: List[tuple[str, object, str]]) -> str:
    """Render named source-column inputs for one case."""
    lines = [f"### {title} inputs", "", "| Source file and column | Value | Unit |", "|---|---:|---|"]
    lines.extend(f"| `{source}` | `{_value(value)}` | {unit} |" for source, value, unit in values)
    return "\n".join(lines)


def _steps_section(title: str, rows: List[Dict[str, str]]) -> str:
    """Render calculation rows for one case."""
    columns = [
        "step", "formula", "unit", "project computed value", "rounded display value",
        "my spreadsheet value", "match?",
    ]
    lines = [f"### {title} calculations", "", "| " + " | ".join(columns) + " |", "|" + "|".join(["---"] * len(columns)) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(row[column]) for column in columns) + " |")
    return "\n".join(lines)


def build_hand_check() -> str:
    """Build the complete hand-check markdown from current CSV inputs."""
    inputs = load_inputs(str(ROOT / "data"))
    links = inputs["links"]
    media = inputs["media"]
    params = inputs["params"].iloc[0]
    options = evaluate_options(inputs["links"], inputs["media"], inputs["params"])
    options = apply_line_codes(options, inputs["params"])
    options = evaluate_availability(options, inputs["params"])
    cat6 = media.loc[media["media"] == "cat6"].iloc[0]
    smf = media.loc[media["media"] == "smf"].iloc[0]
    l2 = links.loc[links["link_id"] == "L2"].iloc[0]
    l6 = links.loc[links["link_id"] == "L6"].iloc[0]
    cat6_l2 = options[(options["link_id"] == "L2") & (options["media"] == "cat6")].iloc[0]
    smf_l6 = options[(options["link_id"] == "L6") & (options["media"] == "smf")].iloc[0]

    transceiver_a = availability(float(params["transceiver_mtbf_h"]), float(params["transceiver_mttr_h"]))
    cat6_cable_mtbf = 1.0 / (float(cat6_l2["cable_failure_rate_per_km"]) * (float(l2["length_m"]) / 1000.0))
    cat6_cable_a = availability(cat6_cable_mtbf, float(cat6_l2["mttr_h"]))
    l2_link_a = link_availability(transceiver_a, cat6_cable_a)
    smf_cable_mtbf = 1.0 / (float(smf_l6["cable_failure_rate_per_km"]) * (float(l6["length_m"]) / 1000.0))
    smf_cable_a = availability(smf_cable_mtbf, float(smf_l6["mttr_h"]))
    l6_link_a = link_availability(transceiver_a, smf_cable_a)
    l6_spare_a = parallel_availability(l6_link_a)

    cat6_rows: List[Dict[str, str]] = []
    cat6_bandwidth = float(cat6["bandwidth_mhz"])
    thermal = thermal_noise_dbm(cat6_bandwidth * 1_000_000.0, float(params["noise_figure_db"]))
    crosstalk_mw = db_to_mw(float(params["crosstalk_noise_dbm"]))
    emi_mw = db_to_mw(float(params["emi_noise_dbm_normal"]))
    thermal_mw = db_to_mw(thermal)
    total_noise = mw_to_dbm(thermal_mw + crosstalk_mw + emi_mw)
    per_pair_shannon = shannon_mbps(cat6_bandwidth, float(cat6_l2["snr_db"]), 1)
    per_pair_nyquist = nyquist_mbps(cat6_bandwidth, int(cat6["signal_levels"]), 1)
    _row(cat6_rows, "attenuation", "22 dB/100 m x 90 m / 100 m", "dB", float(cat6_l2["loss_db"]))
    _row(cat6_rows, "rx power", "tx power - attenuation - connector loss", "dBm", float(cat6_l2["rx_power_dbm"]))
    _row(cat6_rows, "thermal noise", "-174 dBm + 10 log10(B_hz) + noise figure", "dBm", thermal)
    _row(cat6_rows, "thermal noise power", "10^(thermal dBm / 10)", "mW", thermal_mw)
    _row(cat6_rows, "crosstalk noise power", "10^(crosstalk dBm / 10)", "mW", crosstalk_mw)
    _row(cat6_rows, "EMI noise power", "10^(normal EMI dBm / 10)", "mW", emi_mw)
    _row(cat6_rows, "total noise", "10 log10(thermal_mW + crosstalk_mW + EMI_mW)", "dBm", total_noise)
    _row(cat6_rows, "SNR", "rx power - total noise", "dB", float(cat6_l2["snr_db"]))
    _row(cat6_rows, "per-pair Shannon", "B x log2(1 + 10^(SNR/10))", "Mbps", per_pair_shannon)
    _row(cat6_rows, "per-pair Nyquist", "2 x B x log2(M)", "Mbps", per_pair_nyquist)
    _row(cat6_rows, "total Shannon", "pairs x per-pair Shannon", "Mbps", float(cat6_l2["shannon_mbps"]))
    _row(cat6_rows, "total Nyquist", "pairs x per-pair Nyquist", "Mbps", float(cat6_l2["nyquist_mbps"]))
    _row(cat6_rows, "required rate", "target Mbps x safety factor", "Mbps", float(l2["target_mbps"]) * float(params["safety_factor"]))
    _row(cat6_rows, "pass power", "distance <= maximum distance", "boolean", bool(cat6_l2["pass_power"]))
    _row(cat6_rows, "pass SNR", "SNR >= Shannon-derived required SNR", "boolean", bool(cat6_l2["pass_snr"]))
    _row(cat6_rows, "pass rate", "required rate <= Shannon and Nyquist", "boolean", bool(cat6_l2["pass_rate"]))
    _row(cat6_rows, "pass availability", "link availability >= target or spare availability >= target", "boolean", bool(cat6_l2["pass_avail"]))
    _row(cat6_rows, "transceiver availability", "MTBF / (MTBF + MTTR)", "fraction", transceiver_a)
    _row(cat6_rows, "cable availability", "cable MTBF / (cable MTBF + cable MTTR)", "fraction", cat6_cable_a)
    _row(cat6_rows, "link availability", "A_tx x A_cable x A_rx", "fraction", l2_link_a)
    _row(cat6_rows, "downtime per year", "(1 - link availability) x 8760 x 60", "minutes/year", (1.0 - l2_link_a) * 8760.0 * 60.0)
    _row(cat6_rows, "cost", "fixed + (cost/m + install/m) x length", "currency units", option_cost(cat6_l2, use_spare=False))

    smf_rows: List[Dict[str, str]] = []
    smf_bandwidth = float(smf_l6["bandwidth_mhz_km"]) / (float(l6["length_m"]) / 1000.0)
    _row(smf_rows, "fibre loss", "0.35 dB/km x 1.8 km", "dB", float(smf_l6["loss_db"]))
    _row(smf_rows, "connector loss", "CSV connector loss", "dB", float(params["connector_loss_db"]))
    _row(smf_rows, "rx power", "tx power - fibre loss - connector loss", "dBm", float(smf_l6["rx_power_dbm"]))
    _row(smf_rows, "margin", "rx power - receiver sensitivity", "dB", float(smf_l6["margin_db"]))
    _row(smf_rows, "bandwidth at distance", "bandwidth MHz-km / length km", "MHz", smf_bandwidth)
    _row(smf_rows, "availability of one link", "A_tx x A_cable x A_rx", "fraction", l6_link_a)
    _row(smf_rows, "availability with spare", "1 - (1 - A_link)^2", "fraction", l6_spare_a)
    _row(smf_rows, "downtime per year", "(1 - A_with_spare) x 8760 x 60", "minutes/year", (1.0 - l6_spare_a) * 8760.0 * 60.0)
    _row(smf_rows, "cost with spare doubling", "2 x [fixed + (cost/m + install/m) x length]", "currency units", option_cost(smf_l6, use_spare=True))

    l2_inputs = [
        ("data/links.csv:link_id", l2["link_id"], "id"), ("data/links.csv:length_m", l2["length_m"], "m"),
        ("data/links.csv:target_mbps", l2["target_mbps"], "Mbps"), ("data/links.csv:avail_target", l2["avail_target"], "fraction"),
        ("data/links.csv:emi_heavy", l2["emi_heavy"], "boolean"), ("data/media.csv:loss_db_per_100m", cat6["loss_db_per_100m"], "dB/100 m"),
        ("data/media.csv:bandwidth_mhz", cat6["bandwidth_mhz"], "MHz"), ("data/media.csv:signal_levels", cat6["signal_levels"], "levels"),
        ("data/media.csv:pairs", cat6["pairs"], "pairs"), ("data/media.csv:max_distance_m", cat6["max_distance_m"], "m"),
        ("data/media.csv:tx_power_dbm", cat6["tx_power_dbm"], "dBm"), ("data/params.csv:noise_figure_db", params["noise_figure_db"], "dB"),
        ("data/params.csv:connector_loss_db", params["connector_loss_db"], "dB"), ("data/params.csv:crosstalk_noise_dbm", params["crosstalk_noise_dbm"], "dBm"),
        ("data/params.csv:emi_noise_dbm_normal", params["emi_noise_dbm_normal"], "dBm"), ("data/params.csv:safety_factor", params["safety_factor"], "factor"),
        ("data/params.csv:transceiver_mtbf_h", params["transceiver_mtbf_h"], "hours"), ("data/params.csv:transceiver_mttr_h", params["transceiver_mttr_h"], "hours"),
    ]
    l6_inputs = [
        ("data/links.csv:link_id", l6["link_id"], "id"), ("data/links.csv:length_m", l6["length_m"], "m"),
        ("data/links.csv:target_mbps", l6["target_mbps"], "Mbps"), ("data/links.csv:avail_target", l6["avail_target"], "fraction"),
        ("data/media.csv:loss_db_per_km", smf["loss_db_per_km"], "dB/km"), ("data/media.csv:bandwidth_mhz_km", smf["bandwidth_mhz_km"], "MHz-km"),
        ("data/media.csv:max_distance_m", smf["max_distance_m"], "m"), ("data/media.csv:tx_power_dbm", smf["tx_power_dbm"], "dBm"),
        ("data/media.csv:rx_sensitivity_dbm", smf["rx_sensitivity_dbm"], "dBm"), ("data/media.csv:mttr_h", smf["mttr_h"], "hours"),
        ("data/media.csv:cable_failure_rate_per_km", smf["cable_failure_rate_per_km"], "failures/km-hour"), ("data/params.csv:connector_loss_db", params["connector_loss_db"], "dB"),
        ("data/params.csv:transceiver_mtbf_h", params["transceiver_mtbf_h"], "hours"), ("data/params.csv:transceiver_mttr_h", params["transceiver_mttr_h"], "hours"),
    ]
    return "\n".join([
        "# Hand-check material: L2 Cat6 and L6 SMF",
        "",
        "How to use this sheet: copy the inputs into a spreadsheet, build each formula yourself without looking at the code, and compare your result with the project's computed value. Leave the two rightmost columns for your own work.",
        "",
        _inputs_section("L2 Cat6", l2_inputs),
        "",
        _steps_section("L2 Cat6", cat6_rows),
        "",
        _inputs_section("L6 SMF with spare", l6_inputs),
        "",
        _steps_section("L6 SMF with spare", smf_rows),
        "",
    ])


def main() -> None:
    """Write and print the hand-check markdown."""
    output = build_hand_check()
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / "hand_check.md"
    path.write_text(output, encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
