"""Tests for passage building.

    pytest tests/ -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rofact.passages import format_number_ro


@pytest.mark.parametrize("value, decimals, expected", [
    (5.6, None, "5,6"),                 # decimal comma, not a dot
    (19053815, None, "19.053.815"),     # dot between thousands
    (1234.5, 1, "1.234,5"),             # both at once
    (0.25, None, "0,25"),
    (-3.2, None, "-3,2"),
    (1234.0, None, "1.234"),            # a whole float drops the decimals
    (5.6, 2, "5,60"),                   # explicit decimals pad with zeros
    (999, None, "999"),                 # no separator below a thousand
])
def test_format_number_ro(value, decimals, expected):
    assert format_number_ro(value, decimals=decimals) == expected
