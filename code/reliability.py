"""Availability calculations for cable and transceiver failure models."""

import pandas as pd


HOURS_PER_YEAR = 8760.0
MINUTES_PER_HOUR = 60.0


def availability(mtbf_h: float, mttr_h: float) -> float:
    """Calculate availability using ``A = MTBF / (MTBF + MTTR)``."""
    if mtbf_h < 0 or mttr_h < 0 or mtbf_h + mttr_h <= 0:
        raise ValueError("MTBF and MTTR must be non-negative with a positive sum")
    return mtbf_h / (mtbf_h + mttr_h)


def link_availability(transceiver: float, cable: float) -> float:
    """Calculate series link availability using ``A_link = A_tx * A_cable * A_rx``."""
    return transceiver * cable * transceiver


def parallel_availability(link: float) -> float:
    """Calculate two-link parallel availability using ``A = 1 - (1 - A_link)^2``."""
    return 1.0 - (1.0 - link) ** 2


def downtime_per_year(available: float) -> str:
    """Convert unavailability to a year using ``downtime_h = (1 - A) * 8760``."""
    hours = max(0.0, 1.0 - available) * HOURS_PER_YEAR
    if hours < 1.0:
        return f"{hours * MINUTES_PER_HOUR:.1f} min"
    return f"{hours:.1f} h"


def evaluate_availability(options: pd.DataFrame, params: pd.DataFrame) -> pd.DataFrame:
    """Add base availability, spare decision, downtime, and availability pass state."""
    if len(params) != 1:
        raise ValueError("params must contain exactly one row")
    values = params.iloc[0]
    transceiver = availability(float(values["transceiver_mtbf_h"]), float(values["transceiver_mttr_h"]))
    result = options.copy()
    cable = result.apply(
        lambda row: availability(
            1.0 / (float(row["cable_failure_rate_per_km"]) * (float(row["length_m"]) / 1000.0)),
            float(row["mttr_h"]),
        ),
        axis=1,
    )
    result["avail"] = [link_availability(transceiver, value) for value in cable]
    targets = result["avail_target"].astype(float)
    redundant = result["avail"] < targets
    result["redundancy_needed"] = redundant
    result["downtime_per_year"] = [
        downtime_per_year(parallel_availability(value) if needs_spare else value)
        for value, needs_spare in zip(result["avail"], redundant)
    ]
    result["pass_avail"] = [
        value >= target or parallel_availability(value) >= target
        for value, target in zip(result["avail"], targets)
    ]
    return result