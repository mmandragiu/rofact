"""Ingest INS TEMPO Online.

API JSON nedocumentat public, pe port 8077, HTTP simplu. Confirmat funcțional
în 2026-07:

    GET  {BASE}/context/{code}          -> arborele tematic
    GET  {BASE}/matrix/{matrix}         -> metadate + dimensiuni + definiție
    POST {BASE}/matrix/dataSet/{matrix} -> datele  (payload DE VERIFICAT)

Structura răspunsului /matrix/{cod} (ex. POP105A):

    {
      "matrixName": "Populatia rezidenta la 1 ianuarie pe grupe de varsta...",
      "ancestors": [...],
      "definitie": "Populatia rezidenta reprezinta totalitatea persoanelor...",
      "metodologie": "Sursa datelor o constituie cercetarea statistica...",
      "observatii": "Datele sunt disponibile incepand cu anul 2003...",
      "ultimaActualizare": "08-01-2026",
      "periodicitati": ["Anuala"],
      "dimensionsMap": [
        {"dimCode": 1, "label": "Varste si grupe de varsta",
         "options": [{"label": "Total", "nomItemId": 1, "offset": 1}, ...]},
        {"dimCode": 2, "label": "Sexe", "options": [...]},
        ...
      ]
    }

ATENȚIE: textele TEMPO vin FĂRĂ DIACRITICE ("Populatia rezidenta"). Aplică o
normalizare consecventă înainte de indexare, altfel BM25 nu va potrivi
"populația" din afirmație cu "populatia" din pasaj. Vezi TODO-ul de la finalul
fișierului — e o problemă reală, nu una teoretică.
"""

from __future__ import annotations

from datetime import date
from typing import Any, NamedTuple

from rofact.schemas import Document, SnapshotEntry

BASE = "http://statistici.insse.ro:8077/tempo-ins"

TREE_URL = BASE + "/context/{code}"
MATRIX_META_URL = BASE + "/matrix/{matrix}"
MATRIX_DATA_URL = BASE + "/matrix/dataSet/{matrix}"


class Dimension(NamedTuple):
    dim_code: int
    label: str
    options: list[dict[str, Any]]   # {"label", "nomItemId", "offset"}


# --------------------------------------------------------------------------- #
# Navigare și metadate                                                         #
# --------------------------------------------------------------------------- #

def fetch_tree(code: str = "") -> dict:
    """TODO (20 min) — GET pe TREE_URL, întoarce nodul cu `children`.

    Punctele de intrare relevante pentru proiect:
        "1"  -> A. STATISTICA SOCIALA
                 "10" populație și structură demografică
                 "11" mișcarea naturală a populației
                 "12" mișcarea migratorie
                 "15" forța de muncă        <- șomaj, ocupare
                 "20" venituri și condiții de viață
        "2"  -> B. STATISTICA ECONOMICA (verifică denumirea exactă)

    Sugestie: scrie și un `walk_tree(code)` recursiv care listează toate
    matricile dintr-un capitol. Îl rulezi o dată, salvezi rezultatul în
    configs/, și nu mai navighezi la fiecare ingest.
    """
    raise NotImplementedError


def fetch_matrix_meta(matrix: str, snapshot_id: str) -> tuple[dict, SnapshotEntry]:
    """TODO (30 min) — GET pe MATRIX_META_URL, salvează brut, întoarce (json, entry)."""
    raise NotImplementedError


def parse_dimensions(meta: dict) -> list[Dimension]:
    """TODO (15 min) — extrage `dimensionsMap` în listă de Dimension.

    Observație utilă: ultima dimensiune e de obicei unitatea de măsură
    ("UM: Numar persoane"), iar penultima e timpul ("Ani"). Nu presupune
    pozițiile — caută după `label`.
    """
    raise NotImplementedError


# --------------------------------------------------------------------------- #
# Date                                                                         #
# --------------------------------------------------------------------------- #

def fetch_matrix_data(matrix: str, selection: dict[int, list[int]],
                      snapshot_id: str) -> tuple[dict, SnapshotEntry]:
    """Cere datele pentru o selecție de nomItemId per dimensiune.

    !!! PASUL 1, ÎNAINTE DE A SCRIE COD !!!

    Formatul exact al payload-ului POST nu e documentat și se schimbă ocazional.
    Procedura:
      1. deschide https://statistici.insse.ro/tempoins/ în browser;
      2. alege matricea POP105A, selectează o defalcare MICĂ
         (Total / Total / Total / TOTAL / toți anii / Număr persoane);
      3. DevTools -> Network -> apasă butonul de vizualizare;
      4. copiază Request Payload-ul real;
      5. lipește-l aici, în docstring, cu data la care l-ai verificat;
      6. abia apoi scrie funcția.

    Payload verificat la {DATA}:
        TODO: lipește-l aici

    REGULI DE POLITEȚE (nu opționale):
      - delay >= 1.5s între cereri, fără paralelizare;
      - cere defalcări MICI. POP105A are 104 vârste x 3 sexe x 3 medii x 55
        unități teritoriale x 23 ani = ~1.2M celule. Nu ai nevoie de ele și
        cererea e abuzivă. Selectează exact ce îți trebuie;
      - dacă primești 429/503, oprește-te și crește delay-ul.
    """
    raise NotImplementedError


def data_to_documents(matrix: str, meta: dict, data: dict,
                      snapshot_id: str) -> list[Document]:
    """TODO (40 min) — construiește documentele G1 dintr-o matrice.

    Produce DOUĂ tipuri de document, ambele G1:

      1. documentul de DATE — tabelul verbalizat
         document_id = io.stable_id("ins", matrix, snapshot_id)
         source_type = "official_statistics"

      2. documentul de METADATE — `definitie` + `metodologie` + `observatii`
         document_id = io.stable_id("ins_meta", matrix, snapshot_id)
         source_type = "official_methodology"

    Al doilea e mai valoros decât pare. Multe afirmații false se sprijină pe
    confuzii de definiție — "populația rezidentă" (POP105A) vs. "populația după
    domiciliu" (POP107D) diferă cu milioane de persoane. Fără pasajul de
    definiție, un claim de tip `scope_shift` este imposibil de dovedit: ai două
    cifre diferite și nimic care să explice de ce ambele sunt corecte.

    published_at = `ultimaActualizare`, format "DD-MM-YYYY" — parsează-l explicit,
    nu cu dateutil (ar putea citi 08-01-2026 ca 8 ianuarie sau 1 august).
    """
    raise NotImplementedError


# --------------------------------------------------------------------------- #
# Diacritice                                                                   #
# --------------------------------------------------------------------------- #

def restore_diacritics(text: str) -> str:
    """TODO (decizie de proiectare, 30 min) — TEMPO livrează text fără diacritice.

    Ai două opțiuni; alege UNA și aplic-o consecvent în tot corpusul:

    (A) Elimină diacriticele la INDEXARE, în ambele direcții.
        Adaugi în io.py un `fold_diacritics()` aplicat atât pasajelor cât și
        interogărilor, doar la retrieval; textul afișat rămâne cel original.
        + simplu, fără risc de a introduce erori
        + funcționează pentru BM25 și pentru dense
        - pierzi o distincție reală ("peste" vs. "pește" — rar, dar există)

    (B) Restaurează diacriticele cu un model.
        + text mai curat de citit în demo
        - introduci erori într-o sursă G1, ceea ce e inacceptabil: dovada
          trebuie citată exact cum a fost publicată

    RECOMANDARE: (A). Nu modifica niciodată textul unei surse primare. Folosirea
    unei forme normalizate DOAR pentru index e legitimă și se documentează în
    data card.

    Dacă alegi (A), funcția asta dispare și implementezi `fold_diacritics` în io.py.
    """
    raise NotImplementedError


STARTER_MATRICES = {
    "POP105A": dict(label="Populația rezidentă la 1 ianuarie pe grupe de vârstă, sexe, medii",
                    topic="demografie"),
    "POP107D": dict(label="Populația după domiciliu la 1 ianuarie",
                    topic="demografie",
                    note="Perechea POP105A/POP107D = sursă excelentă de claims scope_shift."),
    # TODO: adaugă din capitolul 15 (forța de muncă) matricile de șomaj și ocupare,
    # și din capitolul 20 cele de venituri. Navighează cu fetch_tree.
}
