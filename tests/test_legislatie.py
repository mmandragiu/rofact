"""Tests for legislation ingest and article segmentation.

No network access: the SOAP responses are fixtures.

    pytest tests/ -q
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rofact.ingest import legislatie
from rofact.ingest.legislatie import (
    act_to_document,
    clean_text,
    parse_vigoare,
    pick_act,
    repair_issuer,
)
from rofact.passages import (
    build_passages,
    is_citable_legal_passage,
    segment_by_article,
    segment_document,
    split_sentences,
)
from rofact.schemas import Document, SourceTier


def make_doc(text: str) -> Document:
    return Document(
        document_id="lege_test",
        source_url="https://legislatie.just.ro/Public/DetaliiDocument/1",
        title="Lege de test", source_type="law", source_tier=SourceTier.G2,
        published_at=date(2020, 1, 1), retrieved_at=date(2026, 10, 23),
        snapshot_id="2026-10-23", content_hash="a" * 64, license="test",
        text=clean_text(text),
    )


# --------------------------------------------------------------------------- #
# Cleaning                                                                     #
# --------------------------------------------------------------------------- #

def test_issuer_is_repaired_by_lookup_not_by_guessing():
    """The service mangles ș/ț in metadata. Issuers are a closed set, so they are
    looked up — never reconstructed by guessing which letter a '?' replaced."""
    assert repair_issuer("Pre?edintele României") == "Președintele României"
    assert repair_issuer("Parlamentul") == "Parlamentul"
    # Unknown issuer with lost characters stays as it is, rather than inventing letters.
    assert repair_issuer("Institu?ia Necunoscută") == "Institu?ia Necunoscută"


def test_ascii_tables_become_a_marker_not_silence():
    """A passage that silently dropped a table would look complete while missing
    exactly the numbers a claim may rest on."""
    cleaned = clean_text("Cota este ──────────── de 16%.")
    assert "[…tabel…]" in cleaned
    assert "16%" in cleaned


def test_cleaning_unifies_romanian_diacritics():
    """ş with cedilla and ș with comma both occur in legal texts."""
    assert clean_text("şedinţa") == clean_text("ședința")


def test_parse_vigoare():
    assert parse_vigoare("2015-01-26") == date(2015, 1, 26)
    assert parse_vigoare("") is None


# --------------------------------------------------------------------------- #
# Choosing the right act                                                       #
# --------------------------------------------------------------------------- #

def test_pick_act_prefers_the_act_over_its_norms_and_decrees():
    """Searching 227/2015 returns the law, the consolidated code, the promulgating
    decree and the implementing norms. We want the code itself."""
    results = [
        {"Titlu": "DECRET nr. 718 pentru promulgarea Legii privind Codul fiscal",
         "Text": "x" * 600},
        {"Titlu": "NORME METODOLOGICE de aplicare a Legii nr. 227/2015",
         "Text": "x" * 900_000},
        {"Titlu": "CODUL FISCAL din 8 septembrie 2015", "Text": "x" * 500_000},
    ]
    chosen = pick_act(results, {"contine": "codul fiscal"})
    assert chosen["Titlu"].startswith("CODUL FISCAL")


def test_pick_act_returns_none_when_nothing_found():
    assert pick_act([], {"contine": "ceva"}) is None


# --------------------------------------------------------------------------- #
# Documents                                                                    #
# --------------------------------------------------------------------------- #

def test_act_to_document():
    act = {
        "Titlu": "LEGE nr. 1 din 2020", "Numar": "1", "TipAct": "LEGE",
        "DataVigoare": "2020-01-15",
        "LinkHtml": "http://legislatie.just.ro/Public/DetaliiDocument/4242",
        "Text": "Articolul 1 " + "text de lege. " * 40,
    }
    doc = act_to_document(act, "2026-10-23", "domeniu public")
    assert doc.source_tier == SourceTier.G2
    assert doc.source_type == "law"
    # DataVigoare records which consolidated form was taken: the portal's versions
    # are unofficial, so the date is what makes a verdict reproducible.
    assert doc.published_at == date(2020, 1, 15)
    assert doc.source_url.startswith("https://")      # upgraded from the http link
    assert len(doc.content_hash) == 64


def test_act_with_no_usable_text_is_skipped():
    assert act_to_document({"Text": "prea scurt"}, "2026-10-23", "x") is None


# --------------------------------------------------------------------------- #
# Segmentation                                                                 #
# --------------------------------------------------------------------------- #

LEGE = ("LEGE nr. 1 EMITENT PARLAMENTUL "
        "Articolul 1 Prezenta lege reglementează domeniul X. (1) Cota este de 16%. "
        "Articolul 2 Dispoziții finale conform art. 1 alin. (2). "
        "Articolul 3 " + "introducere lungă. " * 50
        + "(1) Primul punct. " + "detaliu " * 250
        + "(2) Al doilea punct. " + "alt detaliu " * 150)


def test_articles_become_citable_passages():
    """A fact-checker citing "Art. 12 alin. (3)" is usable; one citing "a 150-word
    fragment of law X" is not."""
    passages = segment_by_article(make_doc(LEGE))
    sections = [p.section for p in passages]
    assert sections[:2] == ["Art. 1", "Art. 2"]
    assert "Art. 3 alin. (1)" in sections
    assert "Art. 3 alin. (2)" in sections


def test_long_articles_are_split_by_alineat():
    """One long article must not become a single unsearchable wall of text."""
    passages = segment_by_article(make_doc(LEGE))
    assert all(len(p.text.split()) < 500 for p in passages)


def test_cross_references_are_not_mistaken_for_headings():
    """"conform art. 1 alin. (2)" inside a sentence is a reference, not a new article."""
    passages = segment_by_article(make_doc(LEGE))
    assert len([p for p in passages if p.section == "Art. 2"]) == 1


def test_offsets_point_at_the_real_text():
    """Extractive explanations in S11 depend on these being true positions."""
    doc = make_doc(LEGE)
    for p in segment_by_article(doc):
        assert doc.text[p.char_start:p.char_end].strip()[:20] == p.text[:20]
        assert p.char_end > p.char_start


def test_acts_without_articles_fall_back_to_windows():
    """Methodological norms are numbered by point, not by article."""
    doc = make_doc("NORME METODOLOGICE. " + "Punctul prevede ceva anume. " * 90)
    passages = segment_by_article(doc)
    assert len(passages) > 1
    assert all(p.section is None for p in passages)


def test_window_segmentation_overlaps():
    """A statement sitting on a boundary must appear whole at least once."""
    doc = make_doc("Prima propoziție. " + "O propoziție oarecare aici. " * 80)
    passages = segment_document(doc)
    assert len(passages) > 1
    tail = passages[0].text.split()[-5:]
    assert " ".join(tail) in passages[1].text


@pytest.mark.parametrize("text, expected", [
    ("Conform art. 12 alin. (3) din Legea nr. 227/2015, cota e 16%. Urmează.", 2),
    ("O singură propoziție fără abrevieri.", 1),
    ("Vezi pct. 4 lit. a). Apoi altceva.", 2),
])
def test_romanian_abbreviations_do_not_end_sentences(text, expected):
    assert len(split_sentences(text)) == expected


# --------------------------------------------------------------------------- #
# SOAP plumbing                                                                #
# --------------------------------------------------------------------------- #

def test_search_parses_the_namespaced_response(monkeypatch):
    """Response elements carry the `a:` prefix — a regex without it finds nothing,
    which is how the field was first mistaken for empty."""
    fixture = (
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body>'
        '<SearchResponse xmlns="http://tempuri.org/"><SearchResult '
        'xmlns:a="http://schemas.datacontract.org/2004/07/FreeWebService">'
        "<a:Legi><a:DataVigoare>2015-01-26</a:DataVigoare>"
        "<a:Emitent>Pre?edintele României</a:Emitent>"
        "<a:Numar>227</a:Numar><a:Text>textul actului</a:Text>"
        "<a:Titlu>DECRET nr. 227</a:Titlu></a:Legi>"
        "</SearchResult></SearchResponse></s:Body></s:Envelope>"
    )
    monkeypatch.setattr(legislatie, "_call", lambda op, body: fixture)
    acts = legislatie.search("token", an="2015", numar="227")
    assert len(acts) == 1
    assert acts[0]["Numar"] == "227"
    assert acts[0]["Text"] == "textul actului"


def test_gateway_errors_are_retried_then_reported(monkeypatch):
    """The service answers 502/504 in bursts; a half-finished ingest would leave
    the snapshot incomplete without saying so."""
    import urllib.error

    calls = []

    def always_failing(*args, **kwargs):
        calls.append(1)
        raise urllib.error.HTTPError("url", 504, "Gateway Time-out", {}, None)

    monkeypatch.setattr(legislatie.urllib.request, "urlopen", always_failing)
    monkeypatch.setattr(legislatie.time, "sleep", lambda s: None)
    with pytest.raises(RuntimeError, match="intermitent"):
        legislatie.get_token()
    assert len(calls) == legislatie.RETRIES


def test_client_errors_are_not_retried(monkeypatch):
    """A 404 means the call is wrong; retrying it just hammers the service."""
    import urllib.error

    def not_found(*args, **kwargs):
        raise urllib.error.HTTPError("url", 404, "Not Found", {}, None)

    monkeypatch.setattr(legislatie.urllib.request, "urlopen", not_found)
    with pytest.raises(urllib.error.HTTPError):
        legislatie.get_token()


# --------------------------------------------------------------------------- #
# Corpus budget: which legal passages are worth keeping                        #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("text", [
    "intră în vigoare în termen de minimum 6 luni",
    "cota este de 16%",
    "plafonul de 300.000 lei",
    "venituri de 88.500 euro",
    "începând cu 1 ianuarie 2021",
    "termen de 30 de zile de la comunicare",
])
def test_passages_with_a_quantity_are_kept(text):
    """Legislation claims are restricted to literally verifiable facts, and every
    one of those rests on a number: a threshold, a deadline, a date."""
    assert is_citable_legal_passage(text)


@pytest.mark.parametrize("text", [
    "În înțelesul prezentului cod, sediul permanent este un loc",
    "In intelesul prezentului cod, sediul permanent este un loc",
    "Articolul 7 Definiții ale termenilor comuni",
    "Articolul 7 Definitii ale termenilor comuni",
    "prin producție se înțelege activitatea de",
])
def test_definitions_are_kept_even_without_a_number(text):
    """"The Fiscal Code defines a permanent establishment as ..." is verifiable
    without any quantity. Written to match text with and without diacritics,
    because INS delivers its own text stripped of ș/ț."""
    assert is_citable_legal_passage(text)


@pytest.mark.parametrize("text", [
    "Principiile fiscalității: a) neutralitatea măsurilor fiscale",
    "Aplicarea unitară a prezentului cod se asigură prin Comisia fiscală",
    "prevăzute la art. 2 alin. (2)",          # a cross-reference proves nothing
    "hotărâre definitivă și irevocabilă",     # not a definition
])
def test_passages_with_nothing_verifiable_are_dropped(text):
    assert not is_citable_legal_passage(text)


def test_build_passages_filters_laws_but_can_be_asked_not_to():
    """The eight acts yield 4,077 article passages; official sources must stay at
    20-30% of the corpus or the noise experiment has nothing to measure."""
    doc = make_doc(
        "Articolul 1 Cota este de 16%. "
        "Articolul 2 Principiile generale ale prezentei legi sunt următoarele. "
        "Articolul 3 În înțelesul prezentei legi, termenul X are următorul sens."
    )
    kept = build_passages([doc])
    assert [p.section for p in kept] == ["Art. 1", "Art. 3"]

    everything = build_passages([doc], filter_legal=False)
    assert [p.section for p in everything] == ["Art. 1", "Art. 2", "Art. 3"]
