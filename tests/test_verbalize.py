"""Tests for table verbalisation — turning statistics into searchable sentences.

No network access: the facts are built by hand.

    pytest tests/ -q
"""

from __future__ import annotations

import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rofact.ingest.eurostat import Fact, to_facts
from rofact.passages import verbalize_facts
from rofact.schemas import Document, SourceTier

DOC = Document(
    document_id="estat_test",
    source_url="https://ec.europa.eu/eurostat/databrowser/view/une_rt_a/default/table",
    title="Rata șomajului",
    source_type="official_statistics",
    source_tier=SourceTier.G1,
    published_at=date(2026, 9, 10),
    retrieved_at=date(2026, 10, 20),
    snapshot_id="2026-10-20",
    content_hash="a" * 64,
    license="test",
    text="geo\ttime\tvalue\tflag",
)

GROUP = ("une_rt_a", "rata șomajului", "în rândul persoanelor de 15–74 de ani", "2023")


def fact(geo_code, teritoriu, valoare, start=0):
    return Fact(
        indicator="rata șomajului", teritoriu=teritoriu, geo_code=geo_code, an="2023",
        defalcare="în rândul persoanelor de 15–74 de ani", valoare=valoare, um="%",
        precizare="din populația activă", flag="", group=GROUP,
        char_start=start, char_end=start + 20,
    )


FACTS = [
    fact("RO", "România", 5.6, 0),
    fact("ES", "Spania", 12.2, 20),
    fact("CZ", "Cehia", 2.6, 40),
    fact("EU27_2020", "Uniunea Europeană (27 de state membre)", 6.1, 60),
]


def test_focus_country_gets_three_different_phrasings():
    """One template for the whole official corpus would teach the retriever the
    TEMPLATE instead of the content."""
    own = [p for p in verbalize_facts(DOC, FACTS) if p.template_id != "cmp"]
    assert len(own) == 3
    assert len({p.text for p in own}) == 3                 # genuinely different
    assert len({p.passage_id for p in own}) == 3           # and distinct ids
    assert all("România" in p.text for p in own)
    assert all(p.is_verbalized for p in own)


def test_only_the_focus_country_is_verbalised_row_by_row():
    """The budget rule: 26 other countries must not each get three passages."""
    own = [p for p in verbalize_facts(DOC, FACTS) if p.template_id != "cmp"]
    assert not any("Spania" in p.text or "Cehia" in p.text for p in own)


def test_numbers_use_romanian_convention():
    """'5,6' not '5.6' — real claims use the comma, and BM25 matches characters."""
    own = [p for p in verbalize_facts(DOC, FACTS) if p.template_id != "cmp"]
    assert all("5,6%" in p.text for p in own)
    assert not any("5.6" in p.text for p in own)


def test_every_passage_carries_year_unit_and_indicator():
    """Without the year, `year_shift` claims cannot be told apart; without the
    unit, `unit_swap` and `absolute_vs_percent` cannot be proved."""
    for p in verbalize_facts(DOC, FACTS):
        assert "2023" in p.text
        assert "%" in p.text
        assert "șomajului" in p.text


def test_comparative_passage_ranks_countries_and_separates_the_eu_average():
    comparative = [p for p in verbalize_facts(DOC, FACTS) if p.template_id == "cmp"]
    assert len(comparative) == 1
    text = comparative[0].text
    # Ranked high to low, so a superlative claim can be settled from one passage.
    assert text.index("Spania") < text.index("România") < text.index("Cehia")
    # The aggregate is reported apart: it is not a country and must not win a ranking.
    assert "Media UE-27: 6,1%" in text
    assert text.index("Cehia") < text.index("Media UE-27")


def test_comparative_can_be_switched_off():
    """The selection policy is an argument, not hard-coded: the mentor's answer
    changes a setting, not the function."""
    passages = list(verbalize_facts(DOC, FACTS, comparative=False))
    assert {p.template_id for p in passages} == {"t1", "t2", "t3"}


def test_focus_country_is_configurable():
    passages = [p for p in verbalize_facts(DOC, FACTS, focus_geo="ES")
                if p.template_id != "cmp"]
    assert all("Spania" in p.text for p in passages)


def test_offsets_point_back_into_the_document():
    for p in verbalize_facts(DOC, FACTS):
        assert p.char_end > p.char_start                   # schema invariant
    comparative = next(p for p in verbalize_facts(DOC, FACTS) if p.template_id == "cmp")
    assert comparative.char_start == 0 and comparative.char_end == 80


def test_to_facts_reads_codes_and_offsets():
    doc = DOC.model_copy(update={"text": (
        "freq\tage\tunit\tsex\tgeo\ttime\tvalue\tflag\n"
        "A\tY15-74\tPC_ACT\tT\tRO\t2023\t5.6\t\n"
        "A\tY15-74\tPC_ACT\tT\tES\t2023\t12.2\tp"
    )})
    facts = to_facts(doc, "une_rt_a")
    assert [f.geo_code for f in facts] == ["RO", "ES"]
    assert facts[0].teritoriu == "România"
    assert facts[0].valoare == 5.6
    assert facts[0].defalcare == "în rândul persoanelor de 15–74 de ani"
    assert facts[1].flag == "p"
    # Same indicator and year -> same group -> one comparison.
    assert facts[0].group == facts[1].group
    # Offsets point at the real lines of the table.
    assert doc.text[facts[0].char_start:facts[0].char_end].startswith("A\tY15-74")


def test_template_diversity_is_even():
    """A skewed template mix would be an artefact the model could learn."""
    counts = Counter(p.template_id for p in verbalize_facts(DOC, FACTS))
    assert counts["t1"] == counts["t2"] == counts["t3"] == 1
