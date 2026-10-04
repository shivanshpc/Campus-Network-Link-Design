"""Budget-cut sensitivity analysis using the severity-tiered selector."""

from pathlib import Path
from typing import Dict, List, Tuple

import matplotlib.pyplot as plt
import pandas as pd

from load import load_inputs
from physics import evaluate_options
from linecode import apply_line_codes
from reliability import evaluate_availability
from selection import select_plan_tiered


CUTS = (0, 5, 10, 15, 20, 25, 30)
FAILURE_RATES = (5e-6, 1e-5, 2e-5)
SHORTFALL_COLUMNS = [
    "length_shortfall", "rate_shortfall", "avail_shortfall", "power_shortfall", "snr_shortfall",
]
HARD_COLUMNS = ["length_shortfall", "rate_shortfall", "power_shortfall", "snr_shortfall"]


def _pipeline(rate: float | None = None) -> Tuple[pd.DataFrame, pd.DataFrame, float]:
    """Build evaluated options and return ``(options, links, budget)`` from CSV inputs."""
    inputs = load_inputs()
    media = inputs["media"].copy()
    if rate is not None:
        media["cable_failure_rate_per_km"] = rate
    options = evaluate_options(inputs["links"], media, inputs["params"])
    options = apply_line_codes(options, inputs["params"])
    options = evaluate_availability(options, inputs["params"])
    return options, inputs["links"], float(inputs["params"].iloc[0]["budget"])


def _first_failure(options: pd.DataFrame, budget: float) -> pd.DataFrame:
    """Find each link's smallest 1% cut with nonzero shortfall."""
    rows: List[Dict[str, object]] = []
    for link_id in sorted(options["link_id"].unique()):
        found = None
        for cut in range(101):
            plan, _ = select_plan_tiered(options, budget * (1.0 - cut / 100.0))
            if "total_shortfall" not in plan.columns:
                continue
            row = plan[plan["link_id"] == link_id].iloc[0]
            if float(row["total_shortfall"]) > 0:
                dominant = max(SHORTFALL_COLUMNS, key=lambda column: float(row[column]))
                found = (cut, dominant.replace("_shortfall", ""), float(row["total_shortfall"]))
                break
        rows.append({
            "link_id": link_id,
            "first_failure_cut_pct": found[0] if found else None,
            "dominant_shortfall_type": found[1] if found else "none",
            "first_failure_shortfall": found[2] if found else 0.0,
        })
    return pd.DataFrame(rows)


def _sweep(options: pd.DataFrame, budget: float) -> pd.DataFrame:
    """Evaluate the requested budget cuts with the tiered selector."""
    rows = []
    for cut in CUTS:
        plan, budget_met = select_plan_tiered(options, budget * (1.0 - cut / 100.0))
        shortfall = plan["total_shortfall"] if "total_shortfall" in plan.columns else pd.Series(0.0, index=plan.index)
        hard = plan[HARD_COLUMNS].sum(axis=1) if "total_shortfall" in plan.columns else pd.Series(0.0, index=plan.index)
        soft = plan["avail_shortfall"] if "total_shortfall" in plan.columns else pd.Series(0.0, index=plan.index)
        nonzero = plan.loc[shortfall > 0, "link_id"].tolist() if "total_shortfall" in plan.columns else []
        rows.append({
            "cut_pct": cut,
            "budget": budget * (1.0 - cut / 100.0),
            "total_cost": float(plan["cost"].sum()),
            "budget_met": bool(budget_met),
            "nonzero_shortfall_links": ";".join(nonzero),
            "hard_shortfall_total": float(hard.sum()),
            "soft_shortfall_total": float(soft.sum()),
            **{f"{link_id}_total_shortfall": float(shortfall[plan["link_id"] == link_id].sum()) for link_id in sorted(options["link_id"].unique())},
        })
    return pd.DataFrame(rows)


def run_sensitivity() -> None:
    """Write sensitivity CSV/PNG artifacts and print the 15% interpretation."""
    results_dir = Path("results")
    results_dir.mkdir(parents=True, exist_ok=True)
    options, _, budget = _pipeline()
    sweep = _sweep(options, budget)
    failures = _first_failure(options, budget)
    failure_lookup = failures.set_index("link_id")
    first_links = []
    for _, row in sweep.iterrows():
        nonzero = [link for link in failure_lookup.index if row.get(f"{link}_total_shortfall", 0.0) > 0]
        first_links.append(nonzero[0] if nonzero else "")
    sweep["first_failing_link"] = [
        failures[
            failures["first_failure_cut_pct"].notna()
            & (failures["first_failure_cut_pct"] <= cut)
        ].sort_values(["first_failure_cut_pct", "link_id"]).iloc[0]["link_id"]
        if not failures[
            failures["first_failure_cut_pct"].notna()
            & (failures["first_failure_cut_pct"] <= cut)
        ].empty else ""
        for cut in sweep["cut_pct"]
    ]
    sweep["dominant_shortfall_type"] = [
        failures[
            failures["first_failure_cut_pct"].notna()
            & (failures["first_failure_cut_pct"] <= cut)
        ].sort_values(["first_failure_cut_pct", "link_id"]).iloc[0]["dominant_shortfall_type"]
        if not failures[
            failures["first_failure_cut_pct"].notna()
            & (failures["first_failure_cut_pct"] <= cut)
        ].empty else ""
        for cut in sweep["cut_pct"]
    ]
    ordered_columns = [
        "cut_pct", "budget", "total_cost", "budget_met", "nonzero_shortfall_links",
        "first_failing_link", "dominant_shortfall_type", "hard_shortfall_total", "soft_shortfall_total",
    ] + [f"{link_id}_total_shortfall" for link_id in sorted(options["link_id"].unique())]
    sweep[ordered_columns].to_csv(results_dir / "sensitivity.csv", index=False)

    figure, axis = plt.subplots(figsize=(9, 6))
    for link_id in sorted(options["link_id"].unique()):
        values = sweep[f"{link_id}_total_shortfall"]
        axis.plot(sweep["cut_pct"], values, marker="o", label=f"{link_id} total")
    axis.plot(sweep["cut_pct"], sweep["hard_shortfall_total"], "k--", label="hard total")
    axis.plot(sweep["cut_pct"], sweep["soft_shortfall_total"], "k:", label="soft total")
    axis.set_xlabel("Budget cut (%)")
    axis.set_ylabel("Shortfall")
    axis.set_title("Tiered budget sensitivity")
    axis.legend()
    figure.tight_layout()
    figure.savefig(results_dir / "sensitivity.png", dpi=150)
    plt.close(figure)

    rate_tables = []
    for rate in FAILURE_RATES:
        rate_options, _, rate_budget = _pipeline(rate)
        rate_failures = _first_failure(rate_options, rate_budget)
        rate_failures.insert(0, "cable_failure_rate_per_km", rate)
        rate_tables.append(rate_failures)
    pd.concat(rate_tables, ignore_index=True).to_csv(results_dir / "sensitivity_by_failure_rate.csv", index=False)

    at_15 = sweep[sweep["cut_pct"] == 15].iloc[0]
    link_columns = [f"{link_id}_total_shortfall" for link_id in sorted(options["link_id"].unique())]
    largest_link = max(link_columns, key=lambda column: float(at_15[column])).replace("_total_shortfall", "")
    first = failures.dropna(subset=["first_failure_cut_pct"]).sort_values(["first_failure_cut_pct", "link_id"]).iloc[0]
    headroom = (budget - float(sweep.iloc[0]["total_cost"])) / float(sweep.iloc[0]["total_cost"]) * 100.0
    affected_row = max(
        ((link_id, float(at_15[f"{link_id}_total_shortfall"])) for link_id in sorted(options["link_id"].unique())),
        key=lambda item: item[1],
    )
    actual_15_plan, _ = select_plan_tiered(options, budget * 0.85)
    actual_15_row = actual_15_plan[actual_15_plan["link_id"] == affected_row[0]].iloc[0]
    reason = max(SHORTFALL_COLUMNS, key=lambda column: float(actual_15_row[column])).replace("_shortfall", "")
    print(f"At a 15% cut, {largest_link} is affected because {reason}; the first link to fail as the cut grows is {first['link_id']} at {first['first_failure_cut_pct']:.0f}%. Budget headroom is {headroom:.2f}%, and the result depends on the cable failure rate assumption (table).")
    print("FIRST FAILURE TABLE")
    print(failures.to_string(index=False))
    print("FAILURE-RATE TABLE")
    print(pd.concat(rate_tables, ignore_index=True).to_string(index=False))


if __name__ == "__main__":
    run_sensitivity()
