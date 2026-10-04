import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "code"))

from load import load_inputs
from physics import evaluate_options
from reliability import evaluate_availability
from linecode import apply_line_codes
from selection import select_plan, select_plan_greedy, select_plan_optimal, select_plan_tiered


def _pipeline():
    inputs = load_inputs()
    options = evaluate_options(inputs["links"], inputs["media"], inputs["params"])
    options = apply_line_codes(options, inputs["params"])
    return evaluate_availability(options, inputs["params"]), inputs


def test_plan_is_within_budget_and_has_one_medium_per_link() -> None:
    options, inputs = _pipeline()
    plan = select_plan(options, float(inputs["params"].iloc[0]["budget"]))
    assert plan.cost.sum() <= float(inputs["params"].iloc[0]["budget"])
    assert len(plan) == 6
    assert plan.link_id.nunique() == 6


def test_copper_is_not_chosen_on_emi_link_and_smf_is_chosen_for_l6() -> None:
    options, inputs = _pipeline()
    plan = select_plan(options, float(inputs["params"].iloc[0]["budget"]))
    assert plan.loc[plan.link_id == "L4", "media"].iloc[0] != "cat6"
    assert plan.loc[plan.link_id == "L6", "media"].iloc[0] == "smf"


def test_fifteen_percent_cut_reports_observed_shortfalls_and_moves() -> None:
    options, inputs = _pipeline()
    budget = float(inputs["params"].iloc[0]["budget"])
    plan = select_plan(options, budget * 0.85)
    failing = plan[plan["total_shortfall"] > 0]
    print(f"15% downgrade link: {failing['link_id'].tolist()}; move: {plan.attrs['downgrade_moves']}")
    assert failing["link_id"].tolist() == ["L4", "L6"]
    assert plan.attrs["downgrade_moves"] == [
        "L4: switch to om3 saving 6000.00, harm 0.083",
        "L6: switch to om3 saving 32400.00, harm 0.694",
    ]
    assert plan.attrs["budget_met"] is True


def test_lower_budgets_never_produce_higher_total_cost() -> None:
    options, inputs = _pipeline()
    budget = float(inputs["params"].iloc[0]["budget"])
    totals = [float(select_plan(options, budget * (1.0 - cut))["cost"].sum()) for cut in (0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30)]
    assert totals == sorted(totals, reverse=True)


def test_downgrade_reports_invalid_media_harm_when_it_is_the_best_move() -> None:
    options, inputs = _pipeline()
    budget = float(inputs["params"].iloc[0]["budget"])
    plan = select_plan(options, budget * 0.85)
    assert plan.loc[plan["link_id"] == "L4", "media"].iloc[0] == "om3"
    assert not bool(plan.loc[plan["link_id"] == "L4", "valid"].iloc[0])
    assert plan.loc[plan["link_id"] == "L6", "media"].iloc[0] == "om3"


def test_fifteen_percent_sensitivity_to_cable_failure_rate() -> None:
    inputs = load_inputs()
    budget = float(inputs["params"].iloc[0]["budget"]) * 0.85
    for failure_rate in (5e-6, 1e-5, 2e-5):
        media = inputs["media"].copy()
        media["cable_failure_rate_per_km"] = failure_rate
        options = evaluate_options(inputs["links"], media, inputs["params"])
        options = apply_line_codes(options, inputs["params"])
        options = evaluate_availability(options, inputs["params"])
        plan = select_plan(options, budget)
        failing = plan[plan["total_shortfall"] > 0] if "total_shortfall" in plan.columns else plan.iloc[0:0]
        first_link = failing.sort_values("link_id")["link_id"].iloc[0] if not failing.empty else "none"
        first_move = plan.attrs["downgrade_moves"][0] if plan.attrs["downgrade_moves"] else "none"
        print(f"failure_rate={failure_rate}: first_failing_link={first_link}; first_move={first_move}")
        assert plan.attrs["budget_met"] is True


def test_optimal_shortfall_is_no_worse_than_greedy_at_requested_cuts() -> None:
    options, inputs = _pipeline()
    budget = float(inputs["params"].iloc[0]["budget"])
    for cut in (0.05, 0.10, 0.15, 0.20, 0.25, 0.30):
        greedy = select_plan_greedy(options, budget * (1.0 - cut))
        optimal, _ = select_plan_optimal(options, budget * (1.0 - cut))
        greedy_shortfall = float(greedy["total_shortfall"].sum()) if "total_shortfall" in greedy else 0.0
        optimal_shortfall = float(optimal["total_shortfall"].sum())
        print(f"cut={cut:.0%}: greedy={greedy_shortfall:.6f}; optimal={optimal_shortfall:.6f}")
        assert optimal_shortfall <= greedy_shortfall


def test_tiered_has_no_more_hard_failures_than_equal_weight() -> None:
    options, inputs = _pipeline()
    budget = float(inputs["params"].iloc[0]["budget"])
    hard_columns = ["length_shortfall", "rate_shortfall", "power_shortfall", "snr_shortfall"]
    for cut in (0.05, 0.10, 0.15, 0.20, 0.25, 0.30):
        equal_weight, _ = select_plan_optimal(options, budget * (1.0 - cut))
        tiered, _ = select_plan_tiered(options, budget * (1.0 - cut))
        equal_hard = int((equal_weight[hard_columns].sum(axis=1) > 0).sum())
        tiered_hard = int((tiered[hard_columns].sum(axis=1) > 0).sum())
        print(f"cut={cut:.0%}: equal_hard={equal_hard}; tiered_hard={tiered_hard}")
        assert tiered_hard <= equal_hard


def test_tiered_budget_met_plans_do_not_exceed_budget() -> None:
    options, inputs = _pipeline()
    budget = float(inputs["params"].iloc[0]["budget"])
    for cut in (0.05, 0.10, 0.15, 0.20, 0.25, 0.30):
        plan, budget_met = select_plan_tiered(options, budget * (1.0 - cut))
        if budget_met:
            assert float(plan["cost"].sum()) <= budget * (1.0 - cut)