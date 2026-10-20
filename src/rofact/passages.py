"""Segmentare în pasaje și verbalizarea tabelelor.

Modulul acesta decide ce poate găsi retriever-ul. Un tabel brut este practic
neregăsibil semantic: „5,6" nu se potrivește cu nicio interogare. Verbalizarea
este pasul care transformă statistica în dovadă citabilă.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Iterator

from rofact import io
from rofact.schemas import Document, Passage

# --------------------------------------------------------------------------- #
# Segmentare text narativ                                                      #
# --------------------------------------------------------------------------- #

TARGET_WORDS = 150
OVERLAP_WORDS = 30


def segment_document(doc: Document, *, target_words: int = TARGET_WORDS,
                     overlap_words: int = OVERLAP_WORDS) -> list[Passage]:
    """Segmentează un document narativ în pasaje cu suprapunere.

    TODO (45 min):
      1. împarte textul în propoziții (regex pe [.!?] urmat de spațiu + majusculă;
         atenție la abrevieri românești: „nr.", „art.", „alin.", „lit.", „etc.",
         „dl.", „S.A.", „nr. crt." — o listă de excepții e suficientă, nu-ți
         trebuie spaCy pentru asta);
      2. acumulează propoziții până la ~target_words;
      3. pornește pasajul următor cu ultimele ~overlap_words din cel precedent,
         ca o afirmație aflată la graniță să apară întreagă cel puțin o dată;
      4. char_start / char_end = offset-uri REALE în doc.text — sunt necesare
         pentru explicațiile extractive din S11;
      5. passage_id = io.stable_id("p", doc.document_id, str(char_start)).

    Nu tăia niciodată la mijlocul unei propoziții. Un pasaj trunchiat citat ca
    dovadă arată prost în demo și poate schimba sensul.
    """
    raise NotImplementedError


def segment_by_article(doc: Document) -> list[Passage]:
    """Segmentare pentru texte legislative — pe articol, nu pe fereastră.

    TODO (30 min):
      1. detectează delimitatorii: „Art. 12", „Articolul 12", „ART. 12";
      2. un pasaj = un articol complet (cu alineatele lui); dacă un articol
         depășește ~400 de cuvinte, sparge-l pe alineate „(1)", „(2)";
      3. Passage.section = „Art. 12" sau „Art. 12 alin. (3)".

    De ce contează: un fact-checker care citează „Art. 12 alin. (3)" e util;
    unul care citează „un fragment de 150 de cuvinte din legea X" nu e.
    Secțiunea ajunge direct în citarea afișată de demo.
    """
    raise NotImplementedError


# --------------------------------------------------------------------------- #
# Verbalizarea tabelelor                                                       #
# --------------------------------------------------------------------------- #

# Three phrasings per fact. Several on purpose: if the whole official corpus used
# one template, a dense retriever would learn to match THE TEMPLATE instead of the
# content, and collapse on naturally worded claims — while validation still looked
# fine, because validation uses the same templates.
TEMPLATES = [
    "{Indicator} în {teritoriu}, anul {an}{defalcare}: {valoare}{precizare}.",
    "În {an}, {indicator} în {teritoriu} a fost {valoare}{defalcare}{precizare}.",
    "{teritoriu}, {an} — {indicator}{defalcare}: {valoare}.",
]

COMPARATIVE = "{Indicator}{defalcare}, comparativ în UE, {an}: {clasament}.{medie}"

# Selection policy. Verbalising all 4,504 Eurostat observations three ways would
# give ~13,500 passages — more than the WHOLE corpus target, leaving no room for
# the media noise the research question is about. So: full treatment for the
# country the claims are about, one ranked passage for the rest.
FOCUS_GEO = "RO"
# The EU aggregate is not a country: it is reported apart from the ranking, so a
# claim about "the highest in the EU" is not accidentally settled against an average.
AGGREGATE_GEO = "EU27_2020"


def _capitalize(text: str) -> str:
    return text[:1].upper() + text[1:]


def _value_with_unit(valoare: float, um: str) -> str:
    """'5,6%' · '19.067.576 persoane' · '6,1 la 1.000 de locuitori'."""
    number = format_number_ro(valoare)
    return f"{number}{um}" if um == "%" else f"{number} {um}"


def verbalize_facts(doc: Document, facts: list["Fact"], *,  # noqa: F821
                    focus_geo: str = FOCUS_GEO,
                    aggregate_geo: str = AGGREGATE_GEO,
                    comparative: bool = True) -> Iterator[Passage]:
    """Turn facts into searchable Romanian sentences.

    Two speeds, because the corpus has a budget:

    - the focus country (Romania) gets all three phrasings per fact;
    - every other country is folded into ONE ranked passage per indicator and
      year — which is also the only shape that can settle a claim like "the
      lowest in the EU", since that needs the whole ranking in one place.

    Both knobs are arguments, not hard-coded: a different policy is a different
    call, not a rewrite.
    """
    for fact in facts:
        if fact.geo_code != focus_geo:
            continue
        pieces = dict(
            indicator=fact.indicator,
            Indicator=_capitalize(fact.indicator),
            teritoriu=fact.teritoriu,
            an=fact.an,
            defalcare=f", {fact.defalcare}" if fact.defalcare else "",
            valoare=_value_with_unit(fact.valoare, fact.um),
            precizare=f" ({fact.precizare})" if fact.precizare else "",
        )
        for i, template in enumerate(TEMPLATES, start=1):
            text = template.format(**pieces)
            yield Passage(
                passage_id=io.stable_id("p", doc.document_id,
                                        str(fact.char_start), f"t{i}"),
                document_id=doc.document_id,
                text=text,
                char_start=fact.char_start,
                char_end=fact.char_end,
                section=f"{fact.indicator}, {fact.an}",
                is_verbalized=True,
                template_id=f"t{i}",
            )

    if not comparative:
        return

    groups: dict[tuple, list] = defaultdict(list)
    for fact in facts:
        groups[fact.group].append(fact)

    for group, members in groups.items():
        if len(members) < 2:
            continue
        tari = sorted((f for f in members if f.geo_code != aggregate_geo),
                      key=lambda f: f.valoare, reverse=True)
        agregat = next((f for f in members if f.geo_code == aggregate_geo), None)
        if not tari:
            continue
        head = tari[0]
        clasament = ", ".join(
            f"{f.teritoriu} {_value_with_unit(f.valoare, f.um)}" for f in tari)
        medie = (f" Media UE-27: {_value_with_unit(agregat.valoare, agregat.um)}."
                 if agregat else "")
        text = COMPARATIVE.format(
            Indicator=_capitalize(head.indicator),
            medie=medie,
            defalcare=f", {head.defalcare}" if head.defalcare else "",
            an=head.an,
            clasament=clasament,
        )
        # A comparison spans rows scattered through the table (it is sorted by
        # dimension, not by group), so the offsets cover the whole region.
        yield Passage(
            passage_id=io.stable_id("p", doc.document_id, "cmp", *map(str, group)),
            document_id=doc.document_id,
            text=text,
            char_start=min(f.char_start for f in members),
            char_end=max(f.char_end for f in members),
            section=f"{head.indicator}, {head.an} — comparativ UE",
            is_verbalized=True,
            template_id="cmp",
        )


def format_number_ro(value: float, *, decimals: int | None = None) -> str:
    """Format a number the Romanian way: decimal comma, dot between thousands.

    >>> format_number_ro(5.6)
    '5,6'
    >>> format_number_ro(19053815)
    '19.053.815'
    >>> format_number_ro(1234.5, decimals=1)
    '1.234,5'

    Written by hand instead of using `locale`: locale output depends on the
    machine's settings, so this laptop and CI would disagree.
    """
    if decimals is None:
        if float(value).is_integer():
            decimals = 0
        else:
            # As many decimals as the shortest exact form has: 5.6 -> 1, 0.25 -> 2.
            decimals = max(0, -Decimal(repr(float(value))).as_tuple().exponent)
    text = f"{abs(value):,.{decimals}f}"                                # '1,234.5'
    text = text.replace(",", " ").replace(".", ",").replace(" ", ".")   # '1.234,5'
    return f"-{text}" if value < 0 else text


def build_passages(documents: list[Document]) -> list[Passage]:
    """Dispatcher: pick a segmentation strategy per source type.

        official_statistics  -> verbalise the table
        law                  -> split by article          (S3)
        anything else        -> sliding window            (S3, media and PDFs)
    """
    from rofact.ingest.eurostat import DATA_BROWSER, to_facts

    passages: list[Passage] = []
    for doc in documents:
        if doc.source_type == "official_statistics":
            dataset = doc.source_url.removeprefix(
                DATA_BROWSER.split("{")[0]).split("/")[0]
            passages += verbalize_facts(doc, to_facts(doc, dataset))
        elif doc.source_type == "law":
            passages += segment_by_article(doc)
        else:
            passages += segment_document(doc)
    return passages
