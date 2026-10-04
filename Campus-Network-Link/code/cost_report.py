"""Report plan cost structure and one-at-a-time cost sensitivity."""

from pathlib import Path
from typing import Dict, Tuple

import pandas as pd

import selection
from load import load_inputs
from physics import evaluate_options
from linecode import apply_line_codes
from reliability import evaluate_availability


def _pipeline(media_override: pd.DataFrame | None = None, params_override: pd.DataFrame | None = None) -> Tuple[pd.DataFrame, Dict[str, pd.DataFrame], float]:
    """Build evaluated options and return options, inputs, and budget."""
    inputs = load_inputs()
    media = inputs["media"] if media_override is None else media_override
    params = inputs["params"] if params_override is None else params_override
    options = evaluate_options(inputs["links"], media, params)
    options = apply_line_codes(options, params)
    options = evaluate_availability(options, params)
    return selection.add_costs(options), inputs, float(params.iloc[0]["budget"])


def _valid_cheapest(options: pd.DataFrame) -> pd.DataFrame:
    """Select the cheapest valid option per link."""
    valid = options[options["pass_power"] & options["pass_snr"] & options["pass_rate"] & options["pass_avail"]]
    return valid.sort_values(["link_id", "cost"]).groupby("link_id", as_index=False).first()


def _cost_structure(options: pd.DataFrame, plan: pd.DataFrame) -> pd.DataFrame:
    """Build per-link base, spare, total, and overall-share cost rows."""
    rows = []
    overall = float(plan["cost"].sum())
    for _, selected in plan.iterrows():
        option = options[
            (options["link_id"] == selected["link_id"])
            & (options["media"] == selected["media"])
        ].iloc[0]
        base_cost = selection.option_cost(option, use_spare=False)
        rows.append({
            "link_id": selected["link_id"],
            "cheapest_valid_media": selected["media"],
            "base_cost": base_cost,
            "spare_cost": base_cost if bool(selected["spare"]) else 0.0,
            "total": float(selected["cost"]),
            "share_of_overall_plan_cost": float(selected["cost"]) / overall if overall else 0.0,
        })
    return pd.DataFrame(rows)


def _valid_plan(options: pd.DataFrame) -> pd.DataFrame:
    """Select the cheapest valid option per link without applying the budget fallback."""
    return _valid_cheapest(options)[["link_id", "media", "redundancy_needed", "cost"]].rename(
        columns={"redundancy_needed": "spare"}
    )


def _costed_with_spare_multiplier(options: pd.DataFrame, multiplier: float) -> pd.DataFrame:
    """Recalculate option costs with an in-memory spare multiplier."""
    result = options.copy()
    result["cost"] = result.apply(
        lambda row: selection.option_cost(row, use_spare=False)
        * (multiplier if bool(row["redundancy_needed"]) else 1.0),
        axis=1,
    )
    return result


def _print_plan(label: str, plan: pd.DataFrame) -> None:
    """Print the compact plan view used by each sensitivity case."""
    print(label)
    print(plan[["link_id", "media", "spare", "cost"]].to_string(index=False))
    print(f"total={plan['cost'].sum():.2f}")


def _sensitivity(options: pd.DataFrame, inputs: Dict[str, pd.DataFrame], budget: float) -> Dict[str, float]:
    """Change price, spare multiplier, or failure rate by ±20% in memory."""
    baseline_plan = _valid_plan(options)
    baseline = float(baseline_plan["cost"].sum())
    changes = {}
    cases = []
    for name in ("price", "spare multiplier", "failure rate"):
        values = []
        for factor in (0.8, 1.2):
            media = inputs["media"].copy()
            params = inputs["params"].copy()
            if name == "price":
                media["cost_per_m"] *= factor
                media["install_per_m"] *= factor
            elif name == "failure rate":
                media["cable_failure_rate_per_km"] *= factor
            altered, _, altered_budget = _pipeline(media, params)
            if name == "spare multiplier":
                altered = _costed_with_spare_multiplier(altered, 2.0 * factor)
            plan = _valid_plan(altered)
            values.append(float(plan["cost"].sum()))
            cases.append((name, factor, plan))
        changes[name] = max(abs(value - baseline) for value in values)
    for name, factor, plan in cases:
        old_value = {"price": "1.00x", "spare multiplier": "2.00x", "failure rate": "1e-5"}[name]
        new_value = {
            "price": f"{factor:.2f}x",
            "spare multiplier": f"{2.0 * factor:.2f}x",
            "failure rate": f"{1e-5 * factor:.2g}",
        }[name]
        print(f"{name}: old={old_value}, new={new_value}")
        _print_plan("case plan", plan)
    print(f"baseline valid plan total={baseline:.2f}")
    for name in ("price", "spare multiplier", "failure rate"):
        values = [float(plan["cost"].sum()) for case_name, _, plan in cases if case_name == name]
        print(f"{name}: -20% cost={values[0]:.2f}, +20% cost={values[1]:.2f}, maximum change={changes[name]:.2f}")
    return changes


def _failure_rate_table(inputs: Dict[str, pd.DataFrame]) -> None:
    """Print cheapest-valid cost and spare links over the requested failure rates."""
    rows = []
    for rate in (3e-6, 5e-6, 7.5e-6, 1e-5, 1.5e-5, 2e-5, 3e-5):
        media = inputs["media"].copy()
        media["cable_failure_rate_per_km"] = rate
        options, _, _ = _pipeline(media, inputs["params"])
        plan = _valid_plan(options)
        rows.append({
            "cable_failure_rate_per_km": rate,
            "cheapest_valid_cost": float(plan["cost"].sum()),
            "spare_links": ";".join(plan.loc[plan["spare"], "link_id"]),
        })
    table = pd.DataFrame(rows)
    print("FAILURE-RATE BASELINE COST TABLE")
    print(table.to_string(index=False))
    transceiver = float(inputs["params"].iloc[0]["transceiver_mtbf_h"]) / (
        float(inputs["params"].iloc[0]["transceiver_mtbf_h"])
        + float(inputs["params"].iloc[0]["transceiver_mttr_h"])
    )
    crossings = []
    for link_id in ("L5", "L6"):
        link = inputs["links"].loc[inputs["links"]["link_id"] == link_id].iloc[0]
        smf = inputs["media"].loc[inputs["media"]["media"] == "smf"].iloc[0]
        target = float(link["avail_target"])
        length_km = float(link["length_m"]) / 1000.0
        mttr_h = float(smf["mttr_h"])
        crossing = (transceiver ** 2 / target - 1.0) / (length_km * mttr_h)
        crossings.append({
            "link_id": link_id,
            "cable_mttr_h": mttr_h,
            "analytic_spare_crossing_rate_per_km_hour": crossing,
        })
    crossing_table = pd.DataFrame(crossings)
    print("ANALYTIC SPARE-CROSSING RATES")
    print(crossing_table.to_string(index=False, formatters={
        "analytic_spare_crossing_rate_per_km_hour": "{:.2g}".format,
    }))
    crossing_table.to_csv("results/analytic_spare_crossings.csv", index=False)


def _availability_placeholder_table(inputs: Dict[str, pd.DataFrame]) -> None:
    """Print and save every availability-driving placeholder value and source text."""
    rows = []
    media = inputs["media"]
    for _, row in media.iterrows():
        rows.extend([
            {"name": f"{row['media']}.mtbf_h", "current_value": row["mtbf_h"], "unit": "hours", "source": row["source"]},
            {"name": f"{row['media']}.mttr_h", "current_value": row["mttr_h"], "unit": "hours", "source": row["source"]},
            {"name": f"{row['media']}.cable_failure_rate_per_km", "current_value": row["cable_failure_rate_per_km"], "unit": "failures per km-hour", "source": row["source"]},
        ])
    params = inputs["params"].iloc[0]
    rows.extend([
        {"name": "transceiver_mtbf_h", "current_value": params["transceiver_mtbf_h"], "unit": "hours", "source": params["source"]},
        {"name": "transceiver_mttr_h", "current_value": params["transceiver_mttr_h"], "unit": "hours", "source": params["source"]},
    ])
    table = pd.DataFrame(rows)
    print("AVAILABILITY PLACEHOLDER TABLE")
    print(table.to_string(index=False))
    table.to_csv("results/availability_placeholders.csv", index=False)


def _print_tiered_15_percent_comparison(options: pd.DataFrame, budget: float) -> None:
    """Print capped and uncapped 15% tiered plans for comparison only."""
    columns = [
        "link_id", "media", "spare", "cost", "length_shortfall", "rate_shortfall",
        "avail_shortfall", "power_shortfall", "snr_shortfall", "total_shortfall", "valid",
    ]
    original = selection._normalised_shortfalls

    def capped(row, use_spare):
        values = original(row, use_spare)
        values["avail_shortfall"] = min(1.0, values["avail_shortfall"])
        return values

    try:
        selection._normalised_shortfalls = capped
        before, _ = selection.select_plan_tiered(options, budget * 0.85)
    finally:
        selection._normalised_shortfalls = original
    after, _ = selection.select_plan_tiered(options, budget * 0.85)
    print("15% TIERED PLAN BEFORE CAPPED AVAILABILITY")
    print(before[columns].to_string(index=False))
    print("15% TIERED PLAN AFTER UNCAPPED AVAILABILITY")
    print(after[columns].to_string(index=False))


def main() -> None:
    """Print and save the cost-structure report."""
    options, inputs, budget = _pipeline()
    plan = _valid_plan(options)
    report = _cost_structure(options, plan)
    results_dir = Path("results")
    results_dir.mkdir(parents=True, exist_ok=True)
    report.to_csv(results_dir / "cost_structure.csv", index=False)
    all_smf = float(options[options["media"] == "smf"]["cost"].sum())
    cheapest = float(plan["cost"].sum())
    gap_pct = (all_smf - cheapest) / cheapest * 100.0
    budget_position = (budget - cheapest) / (all_smf - cheapest) * 100.0
    spare_share = float(report["spare_cost"].sum()) / float(report["total"].sum())
    print(report.to_string(index=False))
    print(f"All-SMF total: {all_smf:.2f}")
    print(f"Cheapest valid total: {cheapest:.2f}")
    print(f"Gap: {gap_pct:.2f}%")
    print(f"Budget position inside gap: {budget_position:.2f}%")
    if gap_pct < 15.0:
        print("WARNING: the all-SMF gap is under 15%, so the budget trade-off is relatively narrow.")
    if spare_share > 0.5:
        print("WARNING: spares exceed 50% of plan cost, so reliability redundancy dominates the budget pressure.")
    print("The budget cannot pay for fibre everywhere because fibre and required redundancy remain materially more expensive than copper on short links.")
    changes = _sensitivity(options, inputs, budget)
    print(f"Most sensitive input: {max(changes, key=changes.get)}")
    _availability_placeholder_table(inputs)
    _failure_rate_table(inputs)
    _print_tiered_15_percent_comparison(options, budget)


if __name__ == "__main__":
    main()
