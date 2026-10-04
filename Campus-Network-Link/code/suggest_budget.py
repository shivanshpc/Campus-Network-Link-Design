"""Suggest a budget between all-SMF and cheapest-feasible campus designs."""

import sys

from load import load_inputs
from physics import evaluate_options
from reliability import evaluate_availability
from linecode import apply_line_codes
from selection import add_costs, select_plan


def design_costs() -> tuple[float, float]:
    """Return ``(all_smf_cost, cheapest_feasible_cost)`` from the CSV inputs."""
    inputs = load_inputs()
    options = evaluate_options(inputs["links"], inputs["media"], inputs["params"])
    options = apply_line_codes(options, inputs["params"])
    options = evaluate_availability(options, inputs["params"])
    costed = add_costs(options)
    all_smf = float(costed[costed["media"] == "smf"]["cost"].sum())
    budget_for_selection = max(all_smf, float(inputs["params"].iloc[0]["budget"]))
    cheapest = float(select_plan(options, budget_for_selection)["cost"].sum())
    return all_smf, cheapest


def main() -> None:
    """Print the two design costs and their midpoint budget suggestion."""
    all_smf, cheapest = design_costs()
    low, high = sorted((cheapest, all_smf))
    print(f"All single-mode design: {all_smf:.2f}")
    print(f"Cheapest feasible design: {cheapest:.2f}")
    print(f"Suggested budget: {(low + high) / 2.0:.2f}")


if __name__ == "__main__":
    main()