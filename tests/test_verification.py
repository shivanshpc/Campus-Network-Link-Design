"""Independent audit checks for the existing CEP I.1 toolkit."""

from itertools import product
from pathlib import Path
import math
import re
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).parents[1] / "code"))

from load import load_inputs
from physics import db_to_mw, evaluate_options, mw_to_dbm, shannon_mbps, total_noise_dbm
from reliability import availability, downtime_per_year, link_availability, parallel_availability
from selection import select_plan


ROOT = Path(__file__).parents[1]
RESULTS = ROOT / "results"


def _record(records, check_id, description, expected, actual, passed):
	"""Print and store one audit result."""
	status = "PASS" if passed else "FAIL"
	print(f"{status} {check_id}: actual={actual!r}; expected={expected!r}")
	records.append({
		"check_id": check_id,
		"description": description,
		"expected": str(expected),
		"actual": str(actual),
		"status": status,
	})


def _row(options, link_id, media):
	return options[(options["link_id"] == link_id) & (options["media"] == media)].iloc[0]


def _brute_force(options, budget):
	"""Enumerate all 4^6 combinations using the already-evaluated option rows."""
	link_ids = sorted(options["link_id"].unique())
	media_names = sorted(options["media"].unique())
	rows = {
		(row["link_id"], row["media"]): row
		for _, row in options.iterrows()
	}
	best = None
	combinations_checked = 0
	for choice in product(media_names, repeat=len(link_ids)):
		combinations_checked += 1
		selected = [rows[(link_id, media)] for link_id, media in zip(link_ids, choice)]
		if not all(bool(row["pass_power"]) and bool(row["pass_rate"]) and bool(row["pass_avail"]) for row in selected):
			continue
		cost = sum(float(row["cost"]) for row in selected)
		if cost <= budget and (best is None or cost < best["cost"]):
			best = {"cost": cost, "media": dict(zip(link_ids, choice))}
	return combinations_checked, best


def test_verification() -> None:
	"""Run every requested output, budget, hand-calculation, and brute-force check."""
	records = []
	inputs = load_inputs(str(ROOT / "data"))
	options = pd.read_csv(RESULTS / "options.csv")
	plan = pd.read_csv(RESULTS / "media_plan.csv")
	rejected = pd.read_csv(RESULTS / "rejected.csv")
	params = inputs["params"].iloc[0]
	media = inputs["media"]
	budget = float(params["budget"])

	expected_plan_columns = ["link_id", "bldg_a", "bldg_b", "media", "rate_mbps", "duplex", "line_code", "spare", "cost"]
	_record(records, "P1_COLUMNS", "media_plan columns", expected_plan_columns, list(plan.columns), list(plan.columns) == expected_plan_columns)
	_record(records, "P1_ROWS", "one plan row per link", 6, len(plan), len(plan) == 6 and plan["link_id"].nunique() == 6)
	_record(records, "P1_DUPLICATES", "plan has no duplicate links", 0, int(plan["link_id"].duplicated().sum()), not plan["link_id"].duplicated().any())
	_record(records, "P1_DUPLEX", "all duplex values are full", "full", sorted(plan["duplex"].unique().tolist()), set(plan["duplex"]) == {"full"})

	for link_id in ("L1", "L2"):
		selected_media = plan.loc[plan["link_id"] == link_id, "media"].iloc[0]
		cat6 = _row(options, link_id, "cat6")
		explained = not bool(cat6["pass_power"]) or not bool(cat6["pass_rate"]) or not bool(cat6["pass_avail"])
		_record(records, f"P1_{link_id}_MEDIA", f"{link_id} Cat6 unless options explain rejection", "cat6 or explained failure", selected_media, selected_media == "cat6" or explained)

	l3_plan = plan.loc[plan["link_id"] == "L3"].iloc[0]
	l3_option = _row(options, "L3", l3_plan["media"])
	base_l3 = float(l3_option["fixed_cost"]) + (float(l3_option["cost_per_m"]) + float(l3_option["install_per_m"])) * float(l3_option["length_m"])
	expected_l3_cost = base_l3 + float(params["armoured_surcharge_per_m"]) * float(l3_option["length_m"])
	_record(records, "P1_L3_ARMOUR", "L3 includes no-conduit surcharge", expected_l3_cost, float(l3_plan["cost"]), math.isclose(float(l3_plan["cost"]), expected_l3_cost, rel_tol=1e-9))
	_record(records, "P1_L4_MEDIA", "L4 is not copper", "not cat6", plan.loc[plan["link_id"] == "L4", "media"].iloc[0], plan.loc[plan["link_id"] == "L4", "media"].iloc[0] != "cat6")
	for link_id in ("L5", "L6"):
		value = bool(plan.loc[plan["link_id"] == link_id, "spare"].iloc[0])
		_record(records, f"P1_{link_id}_SPARE", f"{link_id} uses a spare for 99.99% target", True, value, value is True)
	_record(records, "P1_L6_SMF", "L6 uses single-mode fibre", "smf", plan.loc[plan["link_id"] == "L6", "media"].iloc[0], plan.loc[plan["link_id"] == "L6", "media"].iloc[0] == "smf")
	final_cost = float(plan["cost"].sum())
	_record(records, "P1_BUDGET", "plan cost is within params budget", f"<= {budget}", final_cost, final_cost <= budget)
	print("PLAN TABLE")
	print(plan.to_string(index=False))

	l4_rejection = rejected[(rejected["link_id"] == "L4") & (rejected["media"] == "cat6")].iloc[0]
	l4_option = _row(options, "L4", "cat6")
	l4_noise_explained = any(term in (l4_rejection["failed_tests"] + " " + l4_rejection["detail"]).lower() for term in ("noise", "snr"))
	_record(records, "P2_L4_COPPER", "L4 copper rejection is noise/SNR related", "noise/SNR failure", l4_rejection["failed_tests"], l4_noise_explained)
	l6_om3 = rejected[(rejected["link_id"] == "L6") & (rejected["media"] == "om3")].iloc[0]
	_record(records, "P2_L6_OM3", "L6 OM3 rejection names distance or power", "power or distance", l6_om3["failed_tests"] + " / " + l6_om3["detail"], "power" in l6_om3["failed_tests"] or "distance" in l6_om3["detail"].lower())
	all_named = bool((rejected["failed_tests"].fillna("").str.strip() != "").all())
	_record(records, "P2_REJECTION_NAMES", "every rejection names a failing test", True, all_named, all_named)
	print("REJECTED TABLE")
	print(rejected.to_string(index=False))

	required_option_columns = ["loss_db", "rx_power_dbm", "margin_db", "pass_power", "noise_dbm", "snr_db", "shannon_mbps", "nyquist_mbps", "pass_snr", "pass_rate", "line_code", "avail", "redundancy_needed", "pass_avail"]
	missing = sorted(set(required_option_columns) - set(options.columns))
	_record(records, "P3_COLUMNS", "options has required test columns", [], missing, not missing)
	_record(records, "P3_ROWS", "options has 24 Cartesian rows", 24, len(options), len(options) == 24)
	allowed_nan = ((options["media"].isin(["om3", "smf"]) & options["snr_db"].isna()) | (options["media"] == "cat6") & options["margin_db"].isna())
	unexpected_nan = options.drop(columns=[]).isna().any(axis=1) & ~allowed_nan
	_record(records, "P3_NAN", "only non-applicable fibre SNR/copper margin are blank", 0, int(unexpected_nan.sum()), int(unexpected_nan.sum()) == 0)
	spectrum = RESULTS / "line_code_spectrum.png"
	_record(records, "P3_PLOT", "spectrum exists and is non-empty", "> 0 bytes", spectrum.stat().st_size if spectrum.exists() else 0, spectrum.exists() and spectrum.stat().st_size > 0)

	all_smf_cost = float(options[options["media"] == "smf"]["cost"].sum())
	feasible_plan = select_plan(options, budget)
	cheapest_cost = float(feasible_plan["cost"].sum())
	_record(records, "P4_ORDER", "all-SMF cost > budget > cheapest feasible", f"{all_smf_cost} > {budget} > {cheapest_cost}", f"{all_smf_cost} > {budget} > {cheapest_cost}", all_smf_cost > budget > cheapest_cost)
	_record(records, "P4_PLAN_COST", "suggested feasible cost matches plan output", final_cost, cheapest_cost, math.isclose(final_cost, cheapest_cost, rel_tol=1e-9))
	low_budget = budget * 0.85
	low_plan = select_plan(options, low_budget)
	print(f"85% BUDGET PLAN (budget={low_budget:.2f})")
	print(low_plan.to_string(index=False))
	changed = {link: (plan.loc[plan["link_id"] == link, "media"].iloc[0], low_plan.loc[low_plan["link_id"] == link, "media"].iloc[0]) for link in plan["link_id"]}
	print(f"85% changes: {changed}")

	links = inputs["links"].copy()
	cat6_90 = _row(options, "L2", "cat6")
	expected_loss = 22.0 * 90.0 / 100.0
	_record(records, "H1_CAT6_LOSS", "Cat6 90 m attenuation", expected_loss, float(cat6_90["loss_db"]), math.isclose(expected_loss, float(cat6_90["loss_db"]), abs_tol=1e-9))
	links.loc[links["link_id"] == "L2", "length_m"] = 150.0
	altered = evaluate_options(links, inputs["media"], inputs["params"])
	actual_cat6_150 = bool(_row(altered, "L2", "cat6")["pass_power"])
	expected_cat6_150 = 150.0 <= float(media.loc[media["media"] == "cat6", "max_distance_m"].iloc[0])
	_record(records, "H2_CAT6_DISTANCE", "Cat6 150 m power/distance result", expected_cat6_150, actual_cat6_150, actual_cat6_150 == expected_cat6_150)
	smf = media.loc[media["media"] == "smf"].iloc[0]
	l6 = inputs["links"].loc[inputs["links"]["link_id"] == "L6"].iloc[0]
	expected_rx = float(smf["tx_power_dbm"]) - float(smf["loss_db_per_km"]) * (float(l6["length_m"]) / 1000.0) - float(params["connector_loss_db"])
	expected_margin = expected_rx - float(smf["rx_sensitivity_dbm"])
	smf_l6 = _row(options, "L6", "smf")
	_record(records, "H3_SMF_RX", "L6 SMF received power", expected_rx, float(smf_l6["rx_power_dbm"]), math.isclose(expected_rx, float(smf_l6["rx_power_dbm"]), abs_tol=0.05))
	_record(records, "H3_SMF_MARGIN", "L6 SMF margin", expected_margin, float(smf_l6["margin_db"]), math.isclose(expected_margin, float(smf_l6["margin_db"]), abs_tol=0.05))
	om3_l6 = _row(options, "L6", "om3")
	_record(records, "H4_OM3_DISTANCE", "L6 OM3 distance test", False, bool(om3_l6["pass_power"]), not bool(om3_l6["pass_power"]))
	expected_shannon = 100.0 * math.log2(1.0 + 10.0 ** (30.0 / 10.0))
	actual_shannon = shannon_mbps(100.0, 30.0, 1)
	_record(records, "H5_SHANNON", "100 MHz at 30 dB Shannon capacity", expected_shannon, actual_shannon, math.isclose(expected_shannon, actual_shannon, abs_tol=0.001))
	expected_noise = 10.0 * math.log10(10.0 ** (-90.0 / 10.0) + 10.0 ** (-90.0 / 10.0))
	actual_noise = total_noise_dbm(-90.0, -90.0, -300.0)
	_record(records, "H6_NOISE_SUM", "two -90 dBm noise terms sum in power", expected_noise, actual_noise, math.isclose(expected_noise, actual_noise, abs_tol=0.001))
	l2_copper = _row(options, "L2", "cat6")
	_record(records, "H7_EMI_SNR", "L4 copper SNR is lower than L2 copper SNR", f"< {l2_copper['snr_db']}", l4_option["snr_db"], float(l4_option["snr_db"]) < float(l2_copper["snr_db"]))
	cable = media.loc[media["media"] == "om3"].iloc[0]
	trans_a = float(params["transceiver_mtbf_h"]) / (float(params["transceiver_mtbf_h"]) + float(params["transceiver_mttr_h"]))
	cable_mtbf = 1.0 / (float(cable["cable_failure_rate_per_km"]) * (float(inputs["links"].loc[inputs["links"]["link_id"] == "L2", "length_m"].iloc[0]) / 1000.0))
	cable_a = cable_mtbf / (cable_mtbf + float(cable["mttr_h"]))
	expected_avail = trans_a * cable_a * trans_a
	actual_avail = float(_row(options, "L2", "om3")["avail"])
	_record(records, "H8_AVAIL", "series availability is transceiver*cable*transceiver", expected_avail, actual_avail, math.isclose(expected_avail, actual_avail, abs_tol=1e-12))
	expected_parallel = 1.0 - (1.0 - expected_avail) ** 2
	actual_parallel = parallel_availability(actual_avail)
	_record(records, "H8_PARALLEL", "two-link parallel availability", expected_parallel, actual_parallel, math.isclose(expected_parallel, actual_parallel, abs_tol=1e-12))
	_record(records, "H9_DOWNTIME_999", "99.9 percent annual downtime", "about 8.8 h", downtime_per_year(0.999), downtime_per_year(0.999) == "8.8 h")
	_record(records, "H9_DOWNTIME_9999", "99.99 percent annual downtime", "about 52.6 min", downtime_per_year(0.9999), downtime_per_year(0.9999) == "52.6 min")

	combinations, best = _brute_force(options, budget)
	_record(records, "P5_COMBINATIONS", "brute force enumerates 4^6 plans", 4096, combinations, combinations == 4096)
	_record(records, "P5_CHEAPEST", "brute-force cheapest valid plan equals selected plan", final_cost, best["cost"] if best else None, best is not None and math.isclose(final_cost, best["cost"], rel_tol=1e-9))
	low_combinations, low_best = _brute_force(options, low_budget)
	_record(records, "P5_LOW_BUDGET", "brute force at 85 percent budget", "no valid plan within budget", low_best["cost"] if low_best else "no valid plan", low_best is None)
	_record(records, "P5_LOW_ENUM", "low-budget brute force also enumerates 4096 plans", 4096, low_combinations, low_combinations == 4096)

	code_dir = ROOT / "code"
	source = "\n".join(path.read_text(encoding="utf-8") for path in code_dir.glob("*.py"))
	_record(records, "A7_SELECTION_NAME", "selection.py exists and no select import", True, (code_dir / "selection.py").exists() and not bool(re.search(r"(?:from|import)\s+select\b", source)), (code_dir / "selection.py").exists() and not bool(re.search(r"(?:from|import)\s+select\b", source)))
	_record(records, "A8_FIXED_SEED", "random generation has a fixed seed", "seed=2026", "DEFAULT_SEED = 2026" in (code_dir / "linecode.py").read_text(encoding="utf-8"), "DEFAULT_SEED = 2026" in (code_dir / "linecode.py").read_text(encoding="utf-8"))
	physics_source = (code_dir / "physics.py").read_text(encoding="utf-8")
	_record(records, "A2_DB_SUM", "noise conversion uses mW before summing", "db_to_mw and mw_to_dbm", "db_to_mw" in physics_source and "mw_to_dbm" in physics_source, "db_to_mw" in physics_source and "mw_to_dbm" in physics_source)
	_record(records, "A4_AVAIL_UNITS", "availability targets remain fractions", "0.999-style fractions", float(params["budget_cut"]) < 1.0 and float(inputs["links"]["avail_target"].max()) < 1.0, float(inputs["links"]["avail_target"].max()))
	armour_source = (code_dir / "selection.py").read_text(encoding="utf-8")
	armour_check = ("bool(row[\"has_conduit\"]) else" in armour_source and "armoured_surcharge_per_m" in armour_source)
	_record(records, "A5_ARMOUR_RULE", "armour surcharge applies only without conduit", "has_conduit false", armour_check, armour_check)
	_record(records, "A6_COPPER_DISTANCE", "copper distance limit is enforced", "distance_ok", "pass_power = distance_ok" in physics_source and "pass_rate = pass_rate and distance_ok" in physics_source, "pass_power = distance_ok" in physics_source and "pass_rate = pass_rate and distance_ok" in physics_source)

	report = pd.DataFrame(records, columns=["check_id", "description", "expected", "actual", "status"])
	report.to_csv(RESULTS / "verification.csv", index=False)
	failures = report[report["status"] == "FAIL"]
	assert failures.empty, "Audit failures: " + "; ".join(failures["check_id"])
