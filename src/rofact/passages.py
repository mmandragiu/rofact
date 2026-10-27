"""Segmentare în pasaje și verbalizarea tabelelor.

Modulul acesta decide ce poate găsi retriever-ul. Un tabel brut este practic
neregăsibil semantic: „5,6" nu se potrivește cu nicio interogare. Verbalizarea
este pasul care transformă statistica în dovadă citabilă.
"""

from __future__ import annotations

import re
from collections import defaultdict
from decimal import Decimal
from typing import Iterator, NamedTuple

from rofact import io
from rofact.schemas import Document, Passage


class Fact(NamedTuple):
    """One observation, with every piece already phrased in Romanian.

    This is the hand-over point between the two concerns: `eurostat.py` knows what
    the codes mean, `passages.py` knows how to build a Romanian sentence. Neither
    needs to learn the other's job.
    """

    indicator: str      # "rata șomajului"
    teritoriu: str      # "România"
    geo_code: str       # "RO"
    an: str             # "2023"
    defalcare: str      # "în rândul persoanelor de 15–74 de ani", or ""
    valoare: float      # 5.6
    um: str             # "%", "persoane", "milioane de euro", "la 1.000 de locuitori"
    precizare: str      # "din populația activă", or ""
    flag: str           # Eurostat flag, or ""
    group: tuple        # identical for every country of one comparison
    char_start: int     # where the source row sits in Document.text
    char_end: int


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
    # Locate every sentence once, in order. Searching again later (as an earlier
    # version did) finds the FIRST occurrence of a repeated sentence and returns a
    # wrong offset.
    located: list[tuple[int, int, int]] = []        # (start, end, words)
    cursor = 0
    for sentence in split_sentences(doc.text):
        start = doc.text.find(sentence, cursor)
        if start == -1:
            start = cursor
        cursor = start + len(sentence)
        located.append((start, cursor, len(sentence.split())))

    passages: list[Passage] = []
    i = 0
    while i < len(located):
        # Grow a window from sentence i until it reaches the target size. It always
        # holds at least one sentence, however long — never cut mid-sentence.
        j, words = i, 0
        while j < len(located) and (j == i or words < target_words):
            words += located[j][2]
            j += 1

        start, end = located[i][0], located[j - 1][1]
        passages.append(Passage(
            passage_id=io.stable_id("p", doc.document_id, str(start)),
            document_id=doc.document_id,
            text=doc.text[start:end],       # the real slice: offsets are exact
            char_start=start,
            char_end=end,
            is_verbalized=False,
        ))
        if j >= len(located):
            break

        # The next window starts with a tail of this one, but ALWAYS after sentence
        # i. An earlier version could carry the whole window over when it was one
        # long sentence (a formula block, with ';' and no '.'), so the next passage
        # started at the same offset — two passages, one id. Validator check C1
        # caught it on the POP107D methodology.
        k, back = j, 0
        while k - 1 > i and back < overlap_words:
            k -= 1
            back += located[k][2]
        i = k
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

COMPARATIVE = "{Indicator}{defalcare}, {comparatie}, {an}: {clasament}.{medie}"


class Scope(NamedTuple):
    """What a ranking compares, and what its aggregate is called.

    Each source ranks different territories: Eurostat compares EU member states,
    INS compares Romanian counties. The scope was once hard-coded as "comparativ
    în UE" — and a ranking of Teleorman, Vaslui and Dolj came out labelled as an
    EU comparison, with Romania itself ranked among its own counties.
    """

    comparatie: str        # "comparativ în UE" / "pe județe"
    aggregate_geo: str     # the territory reported apart, never ranked
    aggregate_label: str   # "Media UE-27" / "La nivel național"


EU_SCOPE = Scope("comparativ în UE", "EU27_2020", "Media UE-27")
COUNTY_SCOPE = Scope("pe județe", "RO", "La nivel național")

# Selection policy. Verbalising all 4,504 Eurostat observations three ways would
# give ~13,500 passages — more than the WHOLE corpus target, leaving no room for
# the media noise the research question is about. So: full treatment for the
# country the claims are about, one ranked passage for the rest.
FOCUS_GEO = "RO"
# An aggregate (the EU average, Romania's national figure) is not one of the units
# being ranked: it is reported apart, so a claim about "the highest in the EU" or
# "the county with the most unemployment" is never settled against an average.
# Which aggregate applies depends on the source — see Scope.


def _capitalize(text: str) -> str:
    return text[:1].upper() + text[1:]


def _value_with_unit(valoare: float, um: str) -> str:
    """'5,6%' · '19.067.576 persoane' · '6,1 la 1.000 de locuitori'."""
    number = format_number_ro(valoare)
    return f"{number}{um}" if um == "%" else f"{number} {um}"


def verbalize_facts(doc: Document, facts: list[Fact], *,
                    focus_geo: str = FOCUS_GEO,
                    scope: Scope = EU_SCOPE,
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
        tari = sorted((f for f in members if f.geo_code != scope.aggregate_geo),
                      key=lambda f: f.valoare, reverse=True)
        agregat = next((f for f in members if f.geo_code == scope.aggregate_geo), None)
        if not tari:
            continue
        head = tari[0]
        clasament = ", ".join(
            f"{f.teritoriu} {_value_with_unit(f.valoare, f.um)}" for f in tari)
        medie = (f" {scope.aggregate_label}: "
                 f"{_value_with_unit(agregat.valoare, agregat.um)}."
                 if agregat else "")
        text = COMPARATIVE.format(
            Indicator=_capitalize(head.indicator),
            comparatie=scope.comparatie,
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
            section=f"{head.indicator}, {head.an} — {scope.comparatie}",
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


# --------------------------------------------------------------------------- #
# Selecting which legal passages are worth keeping                             #
# --------------------------------------------------------------------------- #
#
# Separate from segmentation on purpose: HOW to cut a text and WHAT to keep are
# different decisions, and only the second one depends on the corpus budget.
#
# Official sources must stay at 20-30% of a 10,000-13,000 passage corpus — the
# rest has to be media, or the noise experiment has nothing to measure. The eight
# acts yield 4,077 article passages on their own, the Fiscal Code 2,689 of them.
#
# The filter follows the claim policy rather than cutting arbitrarily: the
# annotation guide (§7) restricts legislation claims to literally verifiable facts
# — a numeric threshold, a deadline, a date of entry into force — so an article
# with no quantity in it cannot settle one.
# The optional "de" is not cosmetic: Romanian requires it between a number above
# twenty and its unit ("30 de zile", "100 de lei"), so leaving it out silently
# dropped most thresholds in the corpus — exactly the ones claims are made of.
QUANTITY = re.compile(
    r"\d[\d.,]*\s*(?:de\s+)?(%|lei|euro|zile|luni|ani|puncte procentuale)"
    r"|\b(19|20)\d{2}\b"
)

# Explicit exception: "the Fiscal Code defines a permanent establishment as ..."
# is verifiable without any number, and definitions are a genuine claim category
# (the demography domain rests on exactly this kind of distinction).
#
# Written to match text with and without diacritics: legal texts carry them, but
# INS delivers its own text stripped of ș/ț, and the same filter is reused there.
# The endings are spelled out so "definitiv" is not mistaken for "definiție".
DEFINITION = re.compile(
    r"defini[țt]i[ieaț]|[iî]n[țt]eleg|[iî]n[țt]elesul|semnifica[țt]i", re.IGNORECASE
)


def is_citable_legal_passage(text: str) -> bool:
    """Can this passage settle a legislation claim on its own?"""
    return bool(QUANTITY.search(text) or DEFINITION.search(text))


def _matrix_of(doc: Document) -> str:
    """Which INS matrix a document came from, taken from its TEMPO link."""
    return doc.source_url.rsplit("matrix=", 1)[-1]


def build_passages(documents: list[Document], *,
                   filter_legal: bool = True) -> list[Passage]:
    """Dispatcher: pick a segmentation strategy per source type.

        official_statistics  -> verbalise the table
        law                  -> split by article, keep the citable ones
        anything else        -> sliding window            (media and PDFs)

    `filter_legal=False` keeps every article — useful for inspecting what the
    budget filter is throwing away.
    """
    from rofact.ingest.eurostat import DATA_BROWSER, to_facts

    passages: list[Passage] = []
    for doc in documents:
        if doc.source_type == "official_statistics":
            if doc.domain == "insse.ro":
                from rofact.ingest.ins_tempo import to_facts as ins_facts
                facts = ins_facts(doc, _matrix_of(doc))
                scope = COUNTY_SCOPE
            else:
                dataset = doc.source_url.removeprefix(
                    DATA_BROWSER.split("{")[0]).split("/")[0]
                facts = to_facts(doc, dataset)
                scope = EU_SCOPE
            passages += verbalize_facts(doc, facts, scope=scope)
        elif doc.source_type == "law":
            articles = segment_by_article(doc)
            if filter_legal:
                articles = [p for p in articles if is_citable_legal_passage(p.text)]
            passages += articles
        else:
            passages += segment_document(doc)
    return passages
