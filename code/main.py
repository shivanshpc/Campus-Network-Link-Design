"""Run the complete campus media planning pipeline."""

from pathlib import Path

from load import load_inputs
from physics import evaluate_options
from linecode import apply_line_codes, save_spectrum_plot
from reliability import evaluate_availability
from selection import add_costs, rejection_log, select_plan


def run_pipeline() -> None:
    """Load inputs, evaluate all options, select a plan, and write all result artifacts."""
    inputs = load_inputs()
    options = evaluate_options(inputs["links"], inputs["media"], inputs["params"])
    options = apply_line_codes(options, inputs["params"])
    options = evaluate_availability(options, inputs["params"])
    costed_options = add_costs(options)
    budget = float(inputs["params"].iloc[0]["budget"])
    plan = select_plan(options, budget)
    results_dir = Path("results")
    results_dir.mkdir(parents=True, exist_ok=True)
    costed_options.to_csv(results_dir / "options.csv", index=False)
    plan.to_csv(results_dir / "media_plan.csv", index=False)
    rejection_log(costed_options).to_csv(results_dir / "rejected.csv", index=False)
    save_spectrum_plot(str(results_dir / "line_code_spectrum.png"))
    print("Chosen medium per link:")
    for _, row in plan.iterrows():
        print(f"  {row['link_id']}: {row['media']} ({row['cost']:.2f})")
    print(f"Total cost: {plan['cost'].sum():.2f} vs budget {budget:.2f}")
    print(f"Rejected options: {len(rejection_log(costed_options))}")


if __name__ == "__main__":
    run_pipeline()