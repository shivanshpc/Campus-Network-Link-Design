import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "code"))

from reliability import parallel_availability


def test_parallel_availability() -> None:
    link = 0.99
    assert parallel_availability(link) == pytest.approx(1.0 - (1.0 - link) ** 2)