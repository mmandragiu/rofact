"""Segmentare în pasaje și verbalizarea tabelelor.

Modulul acesta decide ce poate găsi retriever-ul. Un tabel brut este practic
neregăsibil semantic: „5,6" nu se potrivește cu nicio interogare. Verbalizarea
este pasul care transformă statistica în dovadă citabilă.
"""

from __future__ import annotations

import re
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


# Romanian abbreviations that end in a dot without ending a sentence. Without
# this list every "art. 12" would be cut in half.
ABBREVIATIONS = {
    "nr", "art", "alin", "lit", "pct", "cap", "par", "etc", "dl", "dna",
    "prof", "dr", "ing", "ec", "av", "jr", "sen", "dep", "ap", "str", "bd",
    "jud", "loc", "com", "nr.crt", "max", "min", "aprox", "ex", "cf", "op",
    "urm", "lei", "mil", "mld", "p", "pp", "vol", "ed", "col", "fig", "tab",
}
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def split_sentences(text: str) -> list[str]:
    """Split into sentences, without breaking on Romanian abbreviations."""
    parts = SENTENCE_END.split(text)
    sentences: list[str] = []
    for part in parts:
        if not part:
            continue
        if sentences:
            tail = sentences[-1].rstrip()
            last_word = tail.rsplit(" ", 1)[-1].rstrip(".").lower()
            # Join back when the previous piece ended on an abbreviation, or on a
            # bare number ("art. 12. Prezentul..." is one reference, not two stops).
            if last_word in ABBREVIATIONS or last_word.isdigit():
                sentences[-1] = f"{tail} {part}"
                continue
        sentences.append(part)
    return sentences


def segment_document(doc: Document, *, target_words: int = TARGET_WORDS,
                     overlap_words: int = OVERLAP_WORDS) -> list[Passage]:
    """Split narrative text into overlapping passages, never mid-sentence.

    The overlap exists so a statement sitting on a boundary appears whole at least
    once: a claim proved by half a sentence is not proved at all. Offsets are real
    positions in `doc.text`, which the extractive explanations in S11 rely on.
    """
    sentences = split_sentences(doc.text)
    passages: list[Passage] = []
    cursor = 0          # how far into doc.text we have consumed
    buffer: list[str] = []
    buffer_start = 0

    def flush(carry: list[str]) -> list[str]:
        if not buffer:
            return []
        text = " ".join(buffer)
        passages.append(Passage(
            passage_id=io.stable_id("p", doc.document_id, str(buffer_start)),
            document_id=doc.document_id,
            text=text,
            char_start=buffer_start,
            char_end=buffer_start + len(text),
            is_verbalized=False,
        ))
        return carry

    for sentence in sentences:
        position = doc.text.find(sentence, cursor)
        if position == -1:
            position = cursor
        cursor = position + len(sentence)

        if not buffer:
            buffer_start = position
        buffer.append(sentence)

        if sum(len(s.split()) for s in buffer) >= target_words:
            # Start the next passage with the tail of this one.
            carry, words = [], 0
            for sentence_back in reversed(buffer):
                if words >= overlap_words:
                    break
                carry.insert(0, sentence_back)
                words += len(sentence_back.split())
            flush(carry)
            buffer = carry
            buffer_start = doc.text.find(carry[0], buffer_start) if carry else cursor

    if buffer and (len(passages) == 0 or " ".join(buffer) != passages[-1].text):
        flush([])
    return passages


# Legal texts arrive as one continuous blob — no line breaks — so article markers
# cannot be anchored to the start of a line. "Articolul 12" is matched anywhere,
# but only when followed by a boundary, so "articolul 12 din Legea X" inside a
# sentence (a cross-reference, not a heading) is not mistaken for one.
ARTICLE = re.compile(r"\bArticolul\s+(\d+(?:\^\d+)?)\s*(?=[A-ZȘȚĂÎÂ(]|\s)")
ALINEAT = re.compile(r"(?<![\w.])\((\d{1,2})\)\s")

ARTICLE_MAX_WORDS = 400


def segment_by_article(doc: Document) -> list[Passage]:
    """Split a legal text by article — the natural unit of citation.

    A fact-checker that cites "Art. 12 alin. (3)" is usable; one that cites "a
    150-word fragment of law X" is not. `Passage.section` carries that reference
    straight into what the demo displays.

    Articles longer than ARTICLE_MAX_WORDS are split further by alineat, so a
    single long article does not become one unsearchable wall of text.

    Acts with no article markers at all (methodological norms are numbered by
    point, not by article) fall back to window segmentation.
    """
    marks = list(ARTICLE.finditer(doc.text))
    if not marks:
        return segment_document(doc)

    passages: list[Passage] = []
    for i, mark in enumerate(marks):
        start = mark.start()
        end = marks[i + 1].start() if i + 1 < len(marks) else len(doc.text)
        body = doc.text[start:end].strip()
        if not body:
            continue
        number = mark.group(1)

        if len(body.split()) <= ARTICLE_MAX_WORDS:
            passages.append(_article_passage(doc, body, start, end, f"Art. {number}"))
            continue

        # Too long: cut at alineat boundaries, keeping the article heading on the
        # first chunk so every piece stays attributable.
        cuts = [m.start() for m in ALINEAT.finditer(body)] or [0]
        if cuts[0] != 0:
            cuts.insert(0, 0)
        cuts.append(len(body))
        for j in range(len(cuts) - 1):
            chunk = body[cuts[j]:cuts[j + 1]].strip()
            if len(chunk.split()) < 5:
                continue
            alineat = ALINEAT.match(body[cuts[j]:])
            section = (f"Art. {number} alin. ({alineat.group(1)})"
                       if alineat else f"Art. {number}")
            passages.append(_article_passage(
                doc, chunk, start + cuts[j], start + cuts[j + 1], section))
    return passages


def _article_passage(doc: Document, text: str, char_start: int, char_end: int,
                     section: str) -> Passage:
    return Passage(
        passage_id=io.stable_id("p", doc.document_id, str(char_start)),
        document_id=doc.document_id,
        text=text,
        char_start=char_start,
        char_end=char_end,
        section=section,
        is_verbalized=False,
    )


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
