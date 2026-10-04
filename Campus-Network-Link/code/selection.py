"""Validity filtering, gradual downgrade selection, and cost reporting."""

from itertools import product
from typing import Dict, List, Tuple

import pandas as pd

from reliability import parallel_availability


_COMBINATION_CACHE = {}


def option_cost(row: pd.Series, use_spare: bool | None = None) -> float:
    """Calculate ``(fixed + media/install + armour) * (2 if spare else 1)``."""
    base = float(row["fixed_cost"]) + (
        float(row["cost_per_m"]) + float(row["install_per_m"])
    ) * float(row["length_m"])
    armour = 0.0 if bool(row["has_conduit"]) else float(row["armoured_surcharge_per_m"]) * float(row["length_m"])
    spare = bool(row["redundancy_needed"]) if use_spare is None else use_spare
    return (base + armour) * (2.0 if spare else 1.0)


def add_costs(options: pd.DataFrame) -> pd.DataFrame:
    """Return options with the calculated spare-aware ``cost`` column."""
    result = options.copy()
    result["cost"] = result.apply(option_cost, axis=1)
    return result


def rejection_log(options: pd.DataFrame) -> pd.DataFrame:
    """Return every failed option with named tests and concise failure details."""
    rows = []
    for _, row in options.iterrows():
        failures: List[str] = []
        details: List[str] = []
        if float(row["length_m"]) > float(row["max_distance_m"]):
            failures.append("distance")
            details.append(f"distance {row['length_m']} m > max {row['max_distance_m']} m")
        if not bool(row["pass_power"]):
            failures.append("power")
            details.append(f"margin/distance failed (margin={row['margin_db']})")
        if "pass_snr" in row and not bool(row["pass_snr"]):
            failures.append("snr")
            details.append(f"snr {row['snr_db']:.1f} dB, emi_heavy={str(bool(row['emi_heavy'])).lower()}")
        if not bool(row["pass_rate"]):
            failures.append("rate")
            details.append(f"rate target {row['target_mbps']} Mbps x safety exceeds Shannon {row['shannon_mbps']:.1f} or Nyquist {row['nyquist_mbps']:.1f} Mbps")
        if not bool(row["pass_avail"]):
            failures.append("availability")
            details.append("availability target unmet even with a spare")
        if failures:
            rows.append({
                "link_id": row["link_id"], "media": row["media"],
                "failed_tests": ";".join(failures), "detail": "; ".join(details),
            })
    return pd.DataFrame(rows, columns=["link_id", "media", "failed_tests", "detail"])


def _valid_options(options: pd.DataFrame) -> pd.DataFrame:
    """Filter options that pass power, SNR, rate, and availability with their required spare."""
    return options[
        options["pass_power"] & options["pass_snr"] & options["pass_rate"] & options["pass_avail"]
    ].copy()


def _plan_rows(options: pd.DataFrame) -> pd.DataFrame:
    """Choose the lowest-cost valid option for each link."""
    valid = _valid_options(options)
    if valid.empty:
        raise ValueError("No valid cable option exists for any link")
    return valid.sort_values(["link_id", "cost"]).groupby("link_id", as_index=False).first()


def _media_plan(chosen: pd.DataFrame) -> pd.DataFrame:
    """Project selected rows to the stable teammate-facing media-plan schema."""
    return chosen[[
        "link_id", "bldg_a", "bldg_b", "media", "target_mbps", "line_code",
        "redundancy_needed", "cost",
    ]].rename(columns={
        "target_mbps": "rate_mbps", "redundancy_needed": "spare",
    }).assign(duplex="full")[[
        "link_id", "bldg_a", "bldg_b", "media", "rate_mbps", "duplex",
        "line_code", "spare", "cost",
    ]]


def _normalised_shortfalls(row: pd.Series, use_spare: bool) -> Dict[str, float]:
    """Calculate capped normalized length, rate, availability, power, and SNR harm."""
    required_rate = float(row["target_mbps"]) * float(row["safety_factor"])
    capacity = min(float(row["shannon_mbps"]), float(row["nyquist_mbps"]))
    availability_value = float(row["avail"])
    if use_spare:
        availability_value = parallel_availability(availability_value)
    margin = float(row["margin_db"])
    snr = float(row["snr_db"])
    required_snr = float(row["required_snr_db"])
    values = {
        "length_shortfall": max(0.0, float(row["length_m"]) - float(row["max_distance_m"])) / float(row["length_m"]),
        "rate_shortfall": max(0.0, required_rate - capacity) / required_rate,
        "avail_shortfall": max(0.0, float(row["avail_target"]) - availability_value) / (1.0 - float(row["avail_target"])),
        "power_shortfall": 0.0 if pd.isna(margin) else max(0.0, float(row["min_margin_db"]) - margin) / float(row["min_margin_db"]),
        "snr_shortfall": 0.0 if pd.isna(snr) else (
            max(0.0, required_snr - snr) / abs(required_snr)
            if required_snr != 0 else abs(required_snr - snr) / 10.0
        ),
    }
    return {
        key: value if key == "avail_shortfall" else min(1.0, value)
        for key, value in values.items()
    }


def _candidate_valid(row: pd.Series, use_spare: bool) -> bool:
    """Evaluate validity for an option under the candidate spare state."""
    available = parallel_availability(float(row["avail"])) if use_spare else float(row["avail"])
    return bool(row["pass_power"]) and bool(row["pass_snr"]) and bool(row["pass_rate"]) and available >= float(row["avail_target"])


def _downgraded_plan(rows: List[Dict[str, object]], budget_met: bool, moves: List[str]) -> pd.DataFrame:
    """Build the extended plan returned when the budget cannot be met."""
    result = pd.DataFrame(rows, columns=[
        "link_id", "media", "spare", "cost", "length_shortfall", "rate_shortfall",
        "avail_shortfall", "power_shortfall", "snr_shortfall", "total_shortfall", "valid",
    ])
    result.attrs["budget_met"] = budget_met
    result.attrs["downgrade_moves"] = moves
    return result


def _move_candidates(options: pd.DataFrame, chosen: pd.DataFrame) -> List[Dict[str, object]]:
    """List spare-removal and cheaper-media moves from the current plan."""
    candidates: List[Dict[str, object]] = []
    for _, current in chosen.iterrows():
        current_cost = float(current["cost"])
        if bool(current["redundancy_needed"]):
            no_spare_cost = option_cost(current, use_spare=False)
            if no_spare_cost < current_cost:
                candidates.append({
                    "link_id": current["link_id"], "media": current["media"], "row": current,
                    "cost": no_spare_cost, "spare": False,
                    "move": f"{current['link_id']}: remove spare from {current['media']}",
                })
        for _, option in options[
            (options["link_id"] == current["link_id"]) & (options["cost"] < current_cost)
        ].iterrows():
            use_spare = bool(option["redundancy_needed"])
            candidate_cost = option_cost(option, use_spare=use_spare)
            if candidate_cost < current_cost:
                candidates.append({
                    "link_id": option["link_id"], "media": option["media"], "row": option,
                    "cost": candidate_cost, "spare": use_spare,
                    "move": f"{option['link_id']}: switch to {option['media']}",
                })
    return candidates


def _score_moves(options: pd.DataFrame, chosen: pd.DataFrame) -> List[Dict[str, object]]:
    """Score all current greedy moves using savings divided by normalized harm."""
    scored = []
    for candidate in _move_candidates(options, chosen):
        shortfalls = _normalised_shortfalls(candidate["row"], bool(candidate["spare"]))
        harm = sum(shortfalls.values())
        savings = float(chosen.loc[chosen["link_id"] == candidate["link_id"], "cost"].iloc[0]) - float(candidate["cost"])
        scored.append({
            **candidate, **shortfalls, "harm": harm, "savings": savings,
            "ratio": savings / (harm + 0.001),
            "resulting_total_cost": float(chosen["cost"].sum()) - savings,
        })
    return scored


def greedy_first_step_table(options_df: pd.DataFrame) -> pd.DataFrame:
    """Return every scored first-step greedy move from the cheapest valid plan."""
    options = add_costs(options_df)
    chosen = _plan_rows(options)
    columns = ["move", "link_id", "media", "spare", "savings", "harm", "ratio", "resulting_total_cost"]
    return pd.DataFrame(_score_moves(options, chosen), columns=columns).sort_values(
        ["ratio", "link_id"], ascending=[False, True], ignore_index=True
    )


def _plan_from_rows(chosen: pd.DataFrame, budget_met: bool, moves: List[str] | None = None) -> pd.DataFrame:
    """Build an extended shortfall plan and attach selection metadata."""
    rows = []
    for _, row in chosen.iterrows():
        use_spare = bool(row["redundancy_needed"])
        shortfalls = _normalised_shortfalls(row, use_spare)
        rows.append({
            "link_id": row["link_id"], "media": row["media"], "spare": use_spare,
            "cost": float(row["cost"]), **shortfalls,
            "total_shortfall": sum(shortfalls.values()),
            "valid": _candidate_valid(row, use_spare),
        })
    result = _downgraded_plan(rows, budget_met, moves or [])
    return result


def select_plan_greedy(options_df: pd.DataFrame, budget: float) -> pd.DataFrame:
    """Select valid options and apply highest-savings-per-harm downgrades when needed."""
    options = add_costs(options_df)
    chosen = _plan_rows(options)
    if float(chosen["cost"].sum()) <= budget:
        result = _media_plan(chosen)
        result.attrs["budget_met"] = True
        result.attrs["downgrade_moves"] = []
        return result

    moves: List[str] = []
    while float(chosen["cost"].sum()) > budget:
        scored = _score_moves(options, chosen)
        if not scored:
            break
        scored.sort(key=lambda item: (-float(item["ratio"]), str(item["link_id"]), str(item["media"])))
        selected = scored[0]
        mask = chosen["link_id"] == selected["link_id"]
        for column in chosen.columns:
            if column in selected["row"]:
                chosen.loc[mask, column] = selected["row"][column]
        chosen.loc[mask, "cost"] = selected["cost"]
        chosen.loc[mask, "redundancy_needed"] = selected["spare"]
        moves.append(f"{selected['move']} saving {selected['savings']:.2f}, harm {selected['harm']:.3f}")

    budget_met = float(chosen["cost"].sum()) <= budget
    result = _plan_from_rows(chosen, budget_met, moves)
    if not budget_met:
        print(f"Budget cannot be met: plan cost {chosen['cost'].sum():.2f} exceeds {budget:.2f}")
    return result


def _state_rows(options: pd.DataFrame) -> Dict[str, List[Tuple[pd.Series, bool, float, float, Dict[str, float]]]]:
    """Build all media/spare states for each link with cost and shortfall score."""
    states: Dict[str, List[Tuple[pd.Series, bool, float, float, Dict[str, float]]]] = {}
    for link_id, group in options.groupby("link_id", sort=True):
        link_states = []
        for _, row in group.iterrows():
            for use_spare in (False, True):
                cost = option_cost(row, use_spare=use_spare)
                shortfall = sum(_normalised_shortfalls(row, use_spare).values())
                state = row.copy()
                state["redundancy_needed"] = use_spare
                state["cost"] = cost
                link_states.append((state, use_spare, cost, shortfall, _normalised_shortfalls(row, use_spare)))
        states[str(link_id)] = link_states
    return states


def _cheapest_states(states: Dict[str, List[Tuple[pd.Series, bool, float, float, Dict[str, float]]]]) -> Tuple[Tuple, ...]:
    """Return the independently cheapest state for each link as the no-fit fallback."""
    return tuple(
        min(
            states[link_id],
            key=lambda state: (state[2], str(state[0]["media"]), int(state[1])),
        )
        for link_id in sorted(states)
    )


def _budget_combinations(
    states: Dict[str, List[Tuple[pd.Series, bool, float, float, Dict[str, float]]]],
    budget: float,
):
    """Yield only combinations whose partial cost can still fit the budget."""
    link_ids = sorted(states)
    minimum_suffix = [0.0] * (len(link_ids) + 1)
    for index in range(len(link_ids) - 1, -1, -1):
        minimum_suffix[index] = minimum_suffix[index + 1] + min(state[2] for state in states[link_ids[index]])

    def visit(index: int, partial: Tuple, partial_cost: float):
        if partial_cost + minimum_suffix[index] > budget:
            return
        if index == len(link_ids):
            yield partial
            return
        for state in states[link_ids[index]]:
            yield from visit(index + 1, partial + (state,), partial_cost + state[2])

    yield from visit(0, tuple(), 0.0)


def _combination_cache(options_df: pd.DataFrame, options: pd.DataFrame, states):
    """Build prefix-best exhaustive plans once for repeated budget queries."""
    cache_key = id(options_df)
    cached = _COMBINATION_CACHE.get(cache_key)
    if cached is not None:
        return cached
    link_ids = sorted(states)
    records = []
    for combination in product(*(states[link_id] for link_id in link_ids)):
        total_cost = sum(state[2] for state in combination)
        shortfalls = [state[4] for state in combination]
        total_shortfall = sum(state[3] for state in combination)
        tie_order = tuple((str(state[0]["media"]), int(state[1])) for state in combination)
        optimal_key = (total_shortfall, total_cost, tie_order)
        hard_values = [sum(values[key] for key in ("length_shortfall", "power_shortfall", "snr_shortfall", "rate_shortfall")) for values in shortfalls]
        tiered_key = (
            sum(value > 0 for value in hard_values),
            sum(hard_values),
            sum(values["avail_shortfall"] for values in shortfalls),
            total_cost,
            tie_order,
        )
        records.append((total_cost, optimal_key, tiered_key, combination))
    records.sort(key=lambda item: item[0])
    costs = [record[0] for record in records]
    optimal_prefix = []
    tiered_prefix = []
    optimal_best = None
    tiered_best = None
    for record in records:
        if optimal_best is None or record[1] < optimal_best[0]:
            optimal_best = (record[1], record[3])
        if tiered_best is None or record[2] < tiered_best[0]:
            tiered_best = (record[2], record[3])
        optimal_prefix.append(optimal_best)
        tiered_prefix.append(tiered_best)
    cached = {
        "costs": costs,
        "optimal_prefix": optimal_prefix,
        "tiered_prefix": tiered_prefix,
        "cheapest": _cheapest_states(states),
    }
    _COMBINATION_CACHE[cache_key] = cached
    return cached


def select_plan_optimal(options_df: pd.DataFrame, budget: float) -> Tuple[pd.DataFrame, bool]:
    """Enumerate every media/spare combination and minimize shortfall within budget.

    Ties use lower total cost, then lexicographic link/media/spare order. If no
    combination fits, the lowest-cost combination is returned with ``False``.
    """
    options = add_costs(options_df)
    states = _state_rows(options)
    link_ids = sorted(states)
    cached = _combination_cache(options_df, options, states)
    import bisect
    index = bisect.bisect_right(cached["costs"], budget) - 1
    budget_met = index >= 0
    selected = cached["optimal_prefix"][index][1] if budget_met else cached["cheapest"]
    chosen = pd.DataFrame([state[0] for state in selected])
    chosen["cost"] = [state[2] for state in selected]
    chosen["redundancy_needed"] = [state[1] for state in selected]
    return _plan_from_rows(chosen, budget_met), budget_met


def select_plan_tiered(options_df: pd.DataFrame, budget: float) -> Tuple[pd.DataFrame, bool]:
    """Choose a budget-fitting plan by hard-failure severity before soft availability harm.

    Length, power, SNR, and rate shortfalls are hard failures. Availability is a
    soft failure because the link can carry traffic while missing its uptime target.
    """
    options = add_costs(options_df)
    states = _state_rows(options)
    link_ids = sorted(states)
    cached = _combination_cache(options_df, options, states)
    import bisect
    index = bisect.bisect_right(cached["costs"], budget) - 1
    budget_met = index >= 0
    selected = cached["tiered_prefix"][index][1] if budget_met else cached["cheapest"]
    chosen = pd.DataFrame([state[0] for state in selected])
    chosen["cost"] = [state[2] for state in selected]
    chosen["redundancy_needed"] = [state[1] for state in selected]
    return _plan_from_rows(chosen, budget_met), budget_met


# Preserve existing callers while exposing the explicit greedy name.
select_plan = select_plan_greedy
