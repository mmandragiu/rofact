"""Ingest Eurostat (JSON-stat 2.0).

Endpoint confirmat funcțional (2026-07):

    https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{dataset}
        ?format=JSON&lang=RO&geo=RO&sex=T&unit=PC_ACT

CAPCANĂ: un cod de dimensiune invalid NU dă eroare HTTP. Întoarce 200 cu
`value: {}` gol și categoria goală în `dimension`. Verifică întotdeauna că ai
primit observații — altfel vei crede că indicatorul nu există.

Exemplu de răspuns (trunchiat):

    {
      "value": {"0": 7.0, "1": 6.8, ...},
      "id":   ["freq", "age", "unit", "sex", "geo", "time"],
      "size": [1, 1, 1, 1, 1, 23],
      "dimension": {
        "time": {"category": {"index": {"2003": 0, ...},
                              "label": {"2003": "2003", ...}}},
        ...
      },
      "extension": {"annotation": [{"type": "UPDATE_DATA", "date": "2026-06-11..."}]}
    }
"""

from __future__ import annotations

from datetime import date
from typing import Any, Iterator, NamedTuple

from rofact.ingest.base import make_entry, polite_get, save_raw
from rofact.schemas import Document, SnapshotEntry, SourceTier

API_BASE = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"


class Observation(NamedTuple):
    """O celulă din tabel, cu toate dimensiunile ei rezolvate în etichete."""

    dataset: str
    value: float
    dims: dict[str, str]        # nume dimensiune (etichetă RO) -> valoare (etichetă RO)
    dim_codes: dict[str, str]   # nume dimensiune (cod) -> valoare (cod)
    time: str                   # extras separat, e mereu ultima dimensiune


def fetch_dataset(dataset: str, snapshot_id: str, *,
                  params: dict[str, Any] | None = None,
                  lang: str = "RO") -> tuple[dict, SnapshotEntry]:
    """Descarcă un dataset și salvează răspunsul brut în snapshot.

    TODO (30 min):
      1. construiește params: {"format": "JSON", "lang": lang, **(params or {})}
      2. polite_get(f"{API_BASE}/{dataset}", params=params)
      3. verifică `resp.json()["value"]` NEVID — dacă e gol, ridică o eroare
         explicită care listează dimensiunile cerute (capcana de mai sus)
      4. save_raw(snapshot_id, "eurostat", dataset, resp.text)
      5. întoarce (json, make_entry(...)) cu n_records = len(value)
    """
    raise NotImplementedError


def iter_observations(payload: dict) -> Iterator[Observation]:
    """Decodează JSON-stat: vectorul plat `value` -> observații cu etichete.

    Cheile din `value` sunt indici LINIARI într-un array multidimensional de
    forma `size`, cu dimensiunile în ordinea din `id`. Decodarea e row-major:

        idx = 12, size = [1, 2, 3]
        -> ultima dimensiune variază cel mai repede
        -> pozițiile se obțin cu divmod succesiv, de la coadă spre cap

    TODO (60 min):
      1. ids   = payload["id"];  sizes = payload["size"]
      2. pentru fiecare dimensiune, construiește index_invers: poziție -> cod,
         din payload["dimension"][d]["category"]["index"]
         (atenție: `index` poate fi dict {cod: poz} SAU listă de coduri)
      3. pentru fiecare (key, val) din payload["value"]:
             idx = int(key)
             poziții = []
             for s in reversed(sizes):
                 idx, r = divmod(idx, s)
                 poziții.append(r)
             poziții.reverse()
      4. mapează pozițiile la coduri, apoi codurile la etichete via
         payload["dimension"][d]["category"]["label"]
      5. yield Observation(...)

    TEST DE CORECTITUDINE (fă-l, nu-l sări):
      ia un dataset mic (ex. une_rt_a filtrat pe geo=RO, sex=T, age=Y15-74),
      decodează, și compară 3 valori cu ce arată Data Browser în interfața web.
      Dacă ordinea dimensiunilor e greșită, obții cifre plauzibile dar false —
      cel mai periculos tip de bug din tot proiectul.
    """
    raise NotImplementedError


def observations_to_documents(observations: list[Observation], dataset: str,
                              snapshot_id: str, *, dataset_label: str,
                              published_at: date | None) -> list[Document]:
    """Grupează observațiile în documente.

    Decizie de proiectare: UN DOCUMENT PER DATASET (nu per observație).
    Documentul e unitatea de proveniență (URL + licență + hash); pasajele
    verbalizate din el sunt unitatea de regăsire. Vezi passages.verbalize_table.

    TODO (30 min):
      - document_id = io.stable_id("estat", dataset, snapshot_id)
      - source_type = "official_statistics", source_tier = SourceTier.G1
      - published_at din extension.annotation[type=UPDATE_DATA] (vezi
        extract_last_update mai jos)
      - text = reprezentarea textuală a tabelului (o linie per observație);
        e ce se hashuiește și ce se segmentează ulterior
      - license din configs/sources.yaml
    """
    raise NotImplementedError


def extract_last_update(payload: dict) -> date | None:
    """TODO (10 min) — caută în payload["extension"]["annotation"] intrarea cu
    type == "UPDATE_DATA" și întoarce data ei. Fallback: payload["updated"].
    Asta devine Document.published_at.
    """
    raise NotImplementedError


# --------------------------------------------------------------------------- #
# Dataset-urile de start (extinde lista în configs/sources.yaml)               #
# --------------------------------------------------------------------------- #

STARTER_DATASETS = {
    "une_rt_a":      dict(label="Rata șomajului, date anuale",     topic="economie",
                          params={"geo": "RO", "sex": "T", "unit": "PC_ACT"}),
    "prc_hicp_aind": dict(label="HICP — rata anuală a inflației",  topic="economie",
                          params={"geo": "RO"}),
    "nama_10_gdp":   dict(label="PIB și componente principale",    topic="economie",
                          params={"geo": "RO"}),
    "demo_gind":     dict(label="Indicatori demografici principali", topic="demografie",
                          params={"geo": "RO"}),
    "ilc_li02":      dict(label="Rata riscului de sărăcie",        topic="statistici_ro_ue",
                          params={"geo": "RO"}),
}
# TODO: pentru claims comparative RO/UE ai nevoie și de geo=EU27_2020 și de
# câteva state vecine (BG, HU, PL). Fără ele, `country_swap` și superlativele
# („cel mai mare din UE") nu pot fi dovedite.
