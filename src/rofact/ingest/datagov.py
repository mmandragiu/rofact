"""Ingest data.gov.ro (CKAN) — domeniul `administratie_publica`.

    GET https://data.gov.ro/api/3/action/package_search?q={query}&rows={n}
    GET https://data.gov.ro/api/3/action/package_show?id={dataset_id}

TODO ÎNAINTE DE ORICE COD (10 min): verifică local că API-ul răspunde. La
testarea inițială a întors gol printr-un proxy. Dacă nu merge, alternativa
pentru administrație publică sunt rapoartele instituționale PDF (pdf_docs.py) —
tot G2, doar mai lent de procesat.
"""

from __future__ import annotations

from rofact.schemas import Document, SnapshotEntry

API_BASE = "https://data.gov.ro/api/3/action"


def search_packages(query: str, rows: int = 50) -> list[dict]:
    """TODO (20 min) — package_search, întoarce result["results"]."""
    raise NotImplementedError


def fetch_package(dataset_id: str, snapshot_id: str) -> tuple[dict, SnapshotEntry]:
    """TODO (20 min) — package_show + salvare brută."""
    raise NotImplementedError


def package_to_documents(pkg: dict, snapshot_id: str) -> list[Document]:
    """TODO (40 min).

    LICENȚA E OBLIGATORIE și diferă per dataset. O iei din `license_id` /
    `license_title` și o pui în Document.license. Validatorul (C10) respinge
    "unknown" pentru G1/G2 — și bine face: un dataset publicabil nu poate avea
    surse cu licență necunoscută.

    `notes` (descrierea CKAN) e text narativ util ca pasaj. Resursele propriu-zise
    (CSV/XLSX) se descarcă separat și se verbalizează ca tabele.
    """
    raise NotImplementedError
