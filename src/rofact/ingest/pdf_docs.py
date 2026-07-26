"""Ingest documente G2 în PDF: rapoarte BNR, Ministerul Finanțelor, rapoarte
de activitate instituționale.

Rolul lor în proiect: TEXT NARATIV oficial. Tabelele G1 dau cifre; PDF-urile dau
context, definiții și formulări apropiate de limbajul afirmațiilor reale. Fără
ele, corpusul G1 e format doar din propoziții verbalizate de tine, iar retriever-ul
învață un registru artificial.
"""

from __future__ import annotations

from pathlib import Path

from rofact.schemas import Document, SnapshotEntry


def fetch_pdf(url: str, snapshot_id: str, source_id: str) -> tuple[Path, SnapshotEntry]:
    """TODO (30 min) — descarcă PDF-ul, salvează brut (ext="pdf"), hash pe fișier."""
    raise NotImplementedError


def extract_text(path: Path) -> str:
    """TODO (45 min) — extragere text cu pdfplumber.

    Atenție la:
      - PDF-uri pe DOUĂ COLOANE: extragerea naivă intercalează liniile din
        coloane diferite și produce text incoerent. pdfplumber permite
        `page.crop((x0, top, x1, bottom))` — taie pe coloane și concatenează.
        Verifică vizual primele pagini înainte să procesezi 200;
      - antete/subsoluri repetate pe fiecare pagină — elimină-le, altfel poluează
        fiecare pasaj și strică BM25;
      - tabele în PDF: `page.extract_tables()` separat; nu le lăsa să curgă în
        text ca șiruri de cifre fără context;
      - PDF-uri SCANATE (fără strat de text): dacă `extract_text()` întoarce
        aproape nimic, e scanat. Nu porni pe OCR — nu merită în bugetul tău.
        Sari peste document și notează în journal.md.
    """
    raise NotImplementedError


def pdf_to_document(path: Path, url: str, snapshot_id: str, *,
                    title: str, published_at, source_type: str = "report") -> Document:
    """TODO (20 min) — asamblează Document (tier G2, hash pe textul normalizat)."""
    raise NotImplementedError


STARTER_DOCS: list[dict] = [
    # TODO (S3): 10-15 documente. Sugestii:
    #   BNR — Raportul asupra inflației (trimestrial)
    #   BNR — Raportul anual
    #   MF — Raportul privind execuția bugetară
    #   INS — comunicate de presă (HTML, mai ușor decât PDF; vezi linkurile din
    #         răspunsurile TEMPO context/*, care trimit direct la comunicate)
]
