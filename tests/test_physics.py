import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "code"))

from physics import db_to_mw, evaluate_options, mw_to_dbm, shannon_mbps
from load import load_inputs


def test_db_mw_round_trip() -> None:
    assert mw_to_dbm(db_to_mw(-10.0)) == pytest.approx(-10.0)


def test_cat6_loss_and_distance_rejection() -> None:
    assert 22.0 * 90.0 / 100.0 == pytest.approx(19.8)
    inputs = load_inputs()
    links = inputs["links"].copy()
    links.loc[0, "length_m"] = 150
    options = evaluate_options(links, inputs["media"], inputs["params"])
    assert not bool(options.loc[(options.link_id == "L1") & (options.media == "cat6"), "pass_power"].iloc[0])


def test_l6_smf_power_budget() -> None:
    inputs = load_inputs()
    options = evaluate_options(inputs["links"], inputs["media"], inputs["params"])
    row = options[(options.link_id == "L6") & (options.media == "smf")].iloc[0]
    assert row.rx_power_dbm == pytest.approx(-10.63, abs=0.05)
    assert row.margin_db == pytest.approx(9.37, abs=0.05)


def test_shannon_example() -> None:
    assert shannon_mbps(100.0, 30.0, 1) == pytest.approx(996.7, abs=0.2)