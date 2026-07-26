"""Teste pentru scheme și pentru validator.

    pytest tests/ -q

Rolul lor: invarianții din schemas.py sunt regulile datasetului. Dacă îi
modifici din greșeală la S6, testele astea te opresc înainte să adnotezi 200 de
claims pe o schemă stricată.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rofact.io import normalize_text, sha256_text, stable_id  # noqa: E402
from rofact.schemas import (  # noqa: E402
    Claim, ClaimPassagePair, CreationMethod, Document, EvidenceQuality, Label,
    Passage, PerturbationType, SourceTier, Split, TextualRelation, Topic,
)

HASH = "a" * 64


def make_claim(**kw):
    base = dict(
        claim_id="ro_000001",
        claim="Rata șomajului în România a fost de 12% în 2023.",
        label=Label.REFUTED,
        topic=Topic.ECONOMIE,
        claim_date=date(2023, 12, 31),
        family_id="somaj_romania_2023",
        creation_method=CreationMethod.REAL_CLAIM,
        gold_evidence_ids=["p_ins_042"],
        annotator_id="mihai",
        annotator_confidence=0.96,
    )
    base.update(kw)
    return Claim(**base)


# --------------------------------------------------------------------------- #
# Claim                                                                        #
# --------------------------------------------------------------------------- #

def test_claim_valid():
    c = make_claim()
    assert c.label == Label.REFUTED
    assert c.gold_evidence_ids == ["p_ins_042"]


def test_nei_cannot_have_gold_evidence():
    """NEI înseamnă „snapshotul nu conține informația". Dacă ai dovadă, nu e NEI."""
    with pytest.raises(ValidationError, match="NOT_ENOUGH_INFO"):
        make_claim(label=Label.NOT_ENOUGH_INFO, gold_evidence_ids=["p_ins_042"])


def test_nei_without_evidence_is_valid():
    c = make_claim(label=Label.NOT_ENOUGH_INFO, gold_evidence_ids=[])
    assert c.gold_evidence_ids == []


def test_supported_requires_evidence():
    with pytest.raises(ValidationError, match="cere cel puțin o dovadă"):
        make_claim(label=Label.SUPPORTED, gold_evidence_ids=[])


def test_constructed_requires_perturbation_type():
    with pytest.raises(ValidationError, match="perturbation_type"):
        make_claim(creation_method=CreationMethod.CONSTRUCTED)


def test_constructed_with_none_perturbation_is_valid():
    """Varianta corectă a unei afirmații construite are perturbation_type=NONE."""
    c = make_claim(creation_method=CreationMethod.CONSTRUCTED,
                   perturbation_type=PerturbationType.NONE)
    assert c.perturbation_type == PerturbationType.NONE


def test_mixed_only_in_challenge():
    with pytest.raises(ValidationError, match="challenge"):
        make_claim(label=Label.MIXED, split=Split.TRAIN)
    ok = make_claim(label=Label.MIXED, split=Split.CHALLENGE)
    assert ok.split == Split.CHALLENGE


def test_multi_evidence_needs_two_passages():
    with pytest.raises(ValidationError, match="requires_multi_evidence"):
        make_claim(requires_multi_evidence=True, gold_evidence_ids=["p1"])


def test_confidence_bounds():
    with pytest.raises(ValidationError):
        make_claim(annotator_confidence=1.4)


def test_extra_fields_rejected():
    """extra='forbid' — o cheie scrisă greșit trebuie să dea eroare, nu să fie
    ignorată tăcut. Altfel adnotezi 300 de claims cu un câmp care nu se salvează."""
    with pytest.raises(ValidationError):
        make_claim(anotator_confidence=0.9)  # typo intenționat


# --------------------------------------------------------------------------- #
# ClaimPassagePair — cele două axe                                             #
# --------------------------------------------------------------------------- #

def test_media_can_support_a_false_claim():
    """Cazul central al proiectului: un articol susține TEXTUAL o afirmație falsă.

    Relația e SUPPORTS, calitatea e MISLEADING, iar eticheta afirmației rămâne
    REFUTED. Dacă testul ăsta pică, metodologia s-a pierdut pe drum.
    """
    pair = ClaimPassagePair(
        claim_id="ro_000001",
        passage_id="p_media_881",
        textual_relation=TextualRelation.SUPPORTS,
        evidence_quality=EvidenceQuality.MISLEADING,
        annotator_id="mihai",
        is_gold=False,
    )
    assert pair.textual_relation == TextualRelation.SUPPORTS
    assert not pair.is_gold


def test_irrelevant_cannot_be_gold():
    with pytest.raises(ValidationError, match="IRRELEVANT"):
        ClaimPassagePair(
            claim_id="ro_000001", passage_id="p_x",
            textual_relation=TextualRelation.IRRELEVANT,
            annotator_id="mihai", is_gold=True,
        )


def test_non_irrelevant_requires_quality():
    with pytest.raises(ValidationError, match="evidence_quality"):
        ClaimPassagePair(
            claim_id="ro_000001", passage_id="p_x",
            textual_relation=TextualRelation.MENTIONS,
            annotator_id="mihai",
        )


def test_gold_requires_strong_quality():
    """Un pasaj UNVERIFIED nu poate fi gold, oricât de bine ar suna."""
    with pytest.raises(ValidationError, match="GOLD_PRIMARY sau CORROBORATIVE"):
        ClaimPassagePair(
            claim_id="ro_000001", passage_id="p_x",
            textual_relation=TextualRelation.SUPPORTS,
            evidence_quality=EvidenceQuality.UNVERIFIED,
            annotator_id="mihai", is_gold=True,
        )


# --------------------------------------------------------------------------- #
# Document / Passage                                                           #
# --------------------------------------------------------------------------- #

def test_document_requires_sha256():
    with pytest.raises(ValidationError, match="sha256"):
        Document(
            document_id="d1", source_url="https://x.ro", title="t",
            source_type="official_statistics", source_tier=SourceTier.G1,
            published_at=date(2024, 1, 20), retrieved_at=date(2026, 7, 21),
            snapshot_id="2026-07-21", content_hash="prea-scurt",
            license="verified", text="…",
        )


def test_passage_offsets():
    with pytest.raises(ValidationError, match="char_end"):
        Passage(passage_id="p1", document_id="d1", text="x",
                char_start=100, char_end=50)


# --------------------------------------------------------------------------- #
# io                                                                           #
# --------------------------------------------------------------------------- #

def test_normalize_unifies_romanian_diacritics():
    """ş/ţ cu sedilă (U+015F/U+0163) vs. ș/ț cu virgulă (U+0219/U+021B).

    Ambele circulă în textele românești. Dacă nu le unifici, același text
    descărcat din două surse produce hash-uri diferite.
    """
    cedilla = "şomaj ţară"      # şomaj ţară
    comma = "șomaj țară"        # șomaj țară
    assert normalize_text(cedilla) == normalize_text(comma)
    assert sha256_text(cedilla) == sha256_text(comma)


def test_normalize_collapses_whitespace():
    assert normalize_text("  a\n\n  b\t c ") == "a b c"


def test_stable_id_is_deterministic():
    """ID-urile nu au voie să depindă de ordinea de procesare — altfel o
    re-rulare a ingest-ului rupe toate adnotările."""
    assert stable_id("ins", "POP105A", "2023") == stable_id("ins", "POP105A", "2023")
    assert stable_id("ins", "POP105A", "2023") != stable_id("ins", "POP105A", "2024")
