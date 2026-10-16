"""Tests for ingest: the source registry and Eurostat decoding.

No test here touches the network — CI must not query Eurostat on every push.

    pytest tests/ -q
"""

from __future__ import annotations

import random
import sys
import warnings
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rofact.ingest import eurostat
from rofact.ingest.base import load_sources_config
from rofact.ingest.eurostat import (
    extract_last_update,
    iter_observations,
    observations_to_documents,
    rows_from_document,
)

# --------------------------------------------------------------------------- #
# load_sources_config                                                          #
# --------------------------------------------------------------------------- #

def test_real_config_loads_without_warnings():
    """Every source in configs/sources.yaml has been verified, so: no warning."""
    with warnings.catch_warnings():
        warnings.simplefilter("error")          # any warning fails the test
        config = load_sources_config()
    assert {"eurostat", "ins_tempo", "legislatie_just"} <= set(config["sources"])


def test_warns_on_unverified_primary_source(tmp_path):
    cfg = tmp_path / "sources.yaml"
    cfg.write_text("sources:\n  x:\n    tier: G1\n    license_status: to_verify\n",
                   encoding="utf-8")
    with pytest.warns(UserWarning, match="to_verify"):
        load_sources_config(cfg)


def test_no_warning_for_unverified_discovery_source(tmp_path):
    """G3 and MEDIA never set a label, so an unverified licence there is not a warning."""
    cfg = tmp_path / "sources.yaml"
    cfg.write_text("sources:\n  x:\n    tier: G3\n    license_status: to_verify\n",
                   encoding="utf-8")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        load_sources_config(cfg)


def test_broken_yaml_gives_clear_error(tmp_path):
    """The bug found on 2026-09-12: the first line of a `>` block not indented."""
    cfg = tmp_path / "sources.yaml"
    cfg.write_text("sources:\n  x:\n    notes: >\n    text\n      more\n", encoding="utf-8")
    with pytest.raises(ValueError, match="nu e YAML valid"):
        load_sources_config(cfg)


# --------------------------------------------------------------------------- #
# Eurostat                                                                     #
# --------------------------------------------------------------------------- #

def make_payload() -> dict:
    """A tiny JSON-stat response: 2 countries x 3 years.

    The trap is built in on purpose: `geo` LISTS Bulgaria first, but Romania has
    POSITION 0. Real responses do this too (they do not follow the request order).
    Decoding by listing order would swap the two countries' numbers.

        position 0 = RO -> keys 0, 1, 2 -> 2021, 2022, 2023
        position 1 = BG -> keys 3, 4, 5
    """
    return {
        "extension": {
            "id": "TEST_DS",
            "annotation": [{"type": "UPDATE_DATA", "date": "2026-09-10T23:00:00+0200"}],
        },
        "id": ["geo", "time"],
        "size": [2, 3],
        "dimension": {
            "geo": {"category": {"index": {"BG": 1, "RO": 0},
                                 "label": {"BG": "Bulgaria", "RO": "Romania"}}},
            "time": {"category": {"index": {"2021": 0, "2022": 1, "2023": 2},
                                  "label": {"2021": "2021", "2022": "2022", "2023": "2023"}}},
        },
        "value": {"0": 5.5, "1": 5.6, "2": 5.4, "3": 5.3, "4": 4.3, "5": 3.5},
        "status": {"5": "p"},
    }


def test_decoding_follows_index_positions_not_listing_order():
    """The most dangerous bug in the project: numbers that look right but aren't."""
    obs = {(o.dim_codes["geo"], o.time): o for o in iter_observations(make_payload())}
    assert obs["RO", "2023"].value == 5.4
    assert obs["BG", "2023"].value == 3.5
    assert obs["BG", "2023"].status == "p"
    assert obs["RO", "2023"].status is None
    assert obs["RO", "2023"].dim_labels["geo"] == "Romania"
    assert obs["RO", "2023"].dataset == "test_ds"


def test_decoding_three_dimensions_row_major():
    """key = a*12 + b*4 + t for size [2, 3, 4]; `index` given as a list this time."""
    payload = {
        "extension": {"id": "X"},
        "id": ["a", "b", "time"],
        "size": [2, 3, 4],
        "dimension": {
            "a": {"category": {"index": ["a0", "a1"], "label": {}}},
            "b": {"category": {"index": ["b0", "b1", "b2"], "label": {}}},
            "time": {"category": {"index": ["t0", "t1", "t2", "t3"], "label": {}}},
        },
        "value": {"0": 0.0, "17": 17.0, "23": 23.0},
    }
    got = {o.value: (o.dim_codes["a"], o.dim_codes["b"], o.time)
           for o in iter_observations(payload)}
    assert got[0.0] == ("a0", "b0", "t0")
    assert got[17.0] == ("a1", "b1", "t1")    # 17 = 1*12 + 1*4 + 1
    assert got[23.0] == ("a1", "b2", "t3")    # 23 = 1*12 + 2*4 + 3


def test_extract_last_update():
    assert extract_last_update(make_payload()) == date(2026, 9, 10)
    assert extract_last_update({"updated": "2025-01-02T10:00:00+0100"}) == date(2025, 1, 2)
    assert extract_last_update({}) is None


def test_fetch_dataset_rejects_empty_response(monkeypatch):
    """Eurostat answers an invalid code with HTTP 200 and `value: {}` — not an error."""
    class FakeResponse:
        text = '{"value": {}}'
        url = "https://example.invalid/une_rt_a"

        def json(self):
            return {"value": {}}

    monkeypatch.setattr(eurostat, "polite_get", lambda *args, **kwargs: FakeResponse())
    with pytest.raises(ValueError, match="cod de dimensiune invalid"):
        eurostat.fetch_dataset("une_rt_a", "2026-09-21", params={"sex": "XX"})


def _document(observations):
    return observations_to_documents(observations, "test_ds", "2026-09-21",
                                     dataset_label="Test", published_at=None,
                                     license="test licence")[0]


def test_document_does_not_depend_on_cell_order():
    """Same data, different arrival order -> same text -> same hash."""
    observations = list(iter_observations(make_payload()))
    shuffled = observations[:]
    random.Random(0).shuffle(shuffled)
    assert shuffled != observations
    assert _document(observations).content_hash == _document(shuffled).content_hash


def test_rows_from_document_adds_romanian_labels():
    rows = rows_from_document(_document(list(iter_observations(make_payload()))))
    ro_2023 = next(r for r in rows if r["geo"] == "RO" and r["time"] == "2023")
    assert ro_2023["geo_ro"] == "România"
    assert ro_2023["value"] == "5.4"
    bg_2023 = next(r for r in rows if r["geo"] == "BG" and r["time"] == "2023")
    assert bg_2023["flag"] == "p"
