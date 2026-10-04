import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parents[1] / "code"))

import cost_report
from load import load_inputs
from physics import evaluate_options
from linecode import apply_line_codes
from reliability import evaluate_availability


ROOT = Path(__file__).parents[1]


def _pipeline():
    inputs = load_inputs()
    options = evaluate_options(inputs["links"], inputs["media"], inputs["params"])
    options = apply_line_codes(options, inputs["params"])
    return evaluate_availability(options, inputs["params"]), inputs


def test_price_sensitivity_is_monotonic_against_baseline_plan() -> None:
    baseline = pd.read_csv(ROOT / "results" / "media_plan.csv")
    inputs = load_inputs()
    options, _, _ = cost_report._pipeline()
    base_total = float(baseline["cost"].sum())
    minus_media = inputs["media"].copy()
    plus_media = inputs["media"].copy()
    minus_media[["cost_per_m", "install_per_m"]] *= 0.8
    plus_media[["cost_per_m", "install_per_m"]] *= 1.2
    minus_options, _, _ = cost_report._pipeline(minus_media, inputs["params"])
    plus_options, _, _ = cost_report._pipeline(plus_media, inputs["params"])
    assert float(cost_report._valid_plan(minus_options)["cost"].sum()) <= base_total
    assert float(cost_report._valid_plan(plus_options)["cost"].sum()) >= base_total


def test_spare_multiplier_matches_no_spare_subtotal() -> None:
    inputs = load_inputs()
    options, _, _ = cost_report._pipeline()
    baseline = pd.read_csv(ROOT / "results" / "media_plan.csv")
    baseline_spares = set(baseline.loc[baseline["spare"], "link_id"])
    no_spare_subtotal = 0.0
    spare_base_total = 0.0
    for _, row in options.iterrows():
        if row["link_id"] in set(baseline["link_id"]):
            if row["link_id"] in baseline_spares and row["media"] == baseline.loc[baseline["link_id"] == row["link_id"], "media"].iloc[0]:
                spare_base_total += cost_report.selection.option_cost(row, use_spare=False)
            if row["media"] == baseline.loc[baseline["link_id"] == row["link_id"], "media"].iloc[0]:
                no_spare_subtotal += cost_report.selection.option_cost(row, use_spare=False)
    totals = []
    for multiplier in (0.8, 1.0, 1.2):
        altered = cost_report._costed_with_spare_multiplier(options, multiplier)
        plan = cost_report._valid_plan(altered)
        assert set(plan.loc[plan["spare"], "link_id"]) == baseline_spares
        total = float(plan["cost"].sum())
        totals.append(total)
        expected = no_spare_subtotal + (multiplier - 1.0) * spare_base_total
        assert total == expected
    assert totals == sorted(totals)


def test_cost_report_baseline_plan_matches_generated_output() -> None:
    baseline = pd.read_csv(ROOT / "results" / "media_plan.csv")
    options, _, _ = cost_report._pipeline()
    report_plan = cost_report._valid_plan(options)
    assert float(report_plan["cost"].sum()) == float(baseline["cost"].sum())
