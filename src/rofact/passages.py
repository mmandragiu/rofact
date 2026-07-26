"""Segmentare în pasaje și verbalizarea tabelelor.

Modulul acesta decide ce poate găsi retriever-ul. Un tabel brut este practic
neregăsibil semantic: „5,6" nu se potrivește cu nicio interogare. Verbalizarea
este pasul care transformă statistica în dovadă citabilă.
"""

from __future__ import annotations

from typing import Iterator

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

TEMPLATES = {
    "rate": [
        "{indicator} în {teritoriu}, {an}{defalcare}: {valoare}{um}.",
        "În {an}, {indicator} {teritoriu_prep} a fost {valoare}{um}{defalcare_prep}.",
        "{indicator}{defalcare_prep} {teritoriu_prep}, anul {an}: {valoare}{um}.",
    ],
    "absolute": [
        "{indicator} în {teritoriu}, {an}{defalcare}: {valoare} {um}.",
        "La nivelul anului {an}, {indicator} {teritoriu_prep} a fost de {valoare} {um}{defalcare_prep}.",
        "{an}, {teritoriu}: {indicator}{defalcare_prep} — {valoare} {um}.",
    ],
}


def verbalize_table(doc: Document, rows: list[dict], *,
                    kind: str = "absolute") -> Iterator[Passage]:
    """Transformă rândurile unui tabel în propoziții regăsibile.

    Exemplu de rezultat dorit:
        „Rata șomajului în România, anul 2023, ambele sexe, total: 5,6%."
        „În 2023, rata șomajului din România a fost 5,6%, pe total sexe."

    TODO (90 min — cea mai importantă oră din S2):

      1. Pentru fiecare rând, umple 2–3 șabloane DIFERITE din TEMPLATES[kind].
         Setează Passage.template_id ca să poți verifica ulterior diversitatea.

         De ce mai multe formulări: dacă tot corpusul G1 folosește un singur
         șablon, retriever-ul dens învață să potrivească ȘABLONUL, nu conținutul.
         Pe afirmații reale, formulate natural, performanța se prăbușește — și
         nu vei înțelege de ce, pentru că pe validation totul arăta bine.

      2. Formatarea numerelor ÎN CONVENȚIE ROMÂNEASCĂ:
           - separator zecimal: VIRGULĂ  -> „5,6" nu „5.6"
           - separator de mii: punct sau spațiu -> „19.053.815" / „19 053 815"
         Afirmațiile reale folosesc virgula. Dacă pasajele tale folosesc punctul,
         potrivirea lexicală (BM25) pe numere eșuează sistematic — exact pe
         categoria de claims care contează cel mai mult.
         Generează AMBELE variante pentru numerele-cheie dacă vrei să fii sigur.

      3. Include unitatea explicit: „%", „persoane", „lei", „milioane lei",
         „puncte procentuale". Fără unitate, claims-urile de tip `unit_swap` și
         `absolute_vs_percent` nu pot fi dovedite.

      4. Include marca temporală în TEXT, nu doar în metadate. Retriever-ul
         caută în text; un pasaj fără an nu poate fi distins de același
         indicator din alt an — și `year_shift` e cea mai frecventă perturbare
         din dataset.

      5. Filtrează celulele irelevante. POP105A are ~1.2M celule. Nu le
         verbaliza pe toate: alege agregatele (Total/Total/TOTAL) plus
         defalcările pe care le folosești efectiv în claims. Corpusul țintă e
         10–13k pasaje în total, nu un milion.

      6. is_verbalized=True pe toate pasajele generate aici. Ai nevoie de
         distincție în data card și în analiza de erori din S10 (pasajele
         verbalizate se comportă altfel decât textul natural).
    """
    raise NotImplementedError


def format_number_ro(value: float, *, decimals: int | None = None) -> str:
    """TODO (20 min) — formatare în convenție românească.

    >>> format_number_ro(5.6)
    '5,6'
    >>> format_number_ro(19053815)
    '19.053.815'
    >>> format_number_ro(1234.5, decimals=1)
    '1.234,5'

    Nu folosi `locale` — depinde de setările sistemului și îți va da rezultate
    diferite pe mașina ta față de CI. Implementează manual.
    """
    raise NotImplementedError


def build_passages(documents: list[Document]) -> list[Passage]:
    """TODO (20 min) — dispecer: alege strategia de segmentare după source_type.

        official_statistics  -> verbalize_table
        law                  -> segment_by_article
        orice altceva        -> segment_document

    Apoi scrie rezultatul cu io.write_jsonl(io.PASSAGES_PATH, passages).
    """
    raise NotImplementedError
