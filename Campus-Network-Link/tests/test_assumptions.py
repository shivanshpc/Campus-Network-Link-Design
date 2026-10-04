from pathlib import Path

import pandas as pd
import pytest


ROOT = Path(__file__).parents[1]


@pytest.mark.xfail(reason="availability placeholders not yet replaced with named citations")
def test_availability_values_have_cited_sources() -> None:
    """Remind us to replace every availability-driving TODO source."""
    media = pd.read_csv(ROOT / "data" / "media.csv")
    params = pd.read_csv(ROOT / "data" / "params.csv")
    availability_sources = list(media["source"].astype(str)) + [str(params.loc[0, "source"])]
    assert not any("TODO" in source for source in availability_sources)