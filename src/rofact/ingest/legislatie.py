"""Ingest legislatie.just.ro — domeniul `legislatie`. Scraping, cu disciplină.

REGULI, în ordine:
  1. Verifică robots.txt ÎNAINTE de primul request (base.check_robots).
     Dacă interzice, oprește-te. Alternativa: descărcare manuală a 20-30 de acte.
  2. delay >= 3s, User-Agent identificabil cu contact.
  3. MAXIM 20-30 de acte normative. Nu indexezi corpusul legislativ — alegi
     actele relevante pentru claims-urile pe care le ai deja.

Capcana majoră: FORMELE CONSOLIDATE. O lege modificată de cinci ori are cinci
forme. Snapshotul trebuie să rețină care formă ai luat și la ce dată era în
vigoare. Altfel afirmațiile despre praguri numerice („cota era 16%") devin
neverificabile — nu poți spune dacă erau 16% la data afirmației sau azi.
"""

from __future__ import annotations

from datetime import date

from rofact.schemas import Document, SnapshotEntry


def fetch_act(url: str, snapshot_id: str) -> tuple[str, SnapshotEntry]:
    """TODO (60 min) — descarcă un act, salvează HTML-ul brut.

    Pași:
      1. base.check_robots pentru URL;
      2. base.polite_get cu delay=3;
      3. save_raw(..., ext="html");
      4. întoarce (html, entry).
    """
    raise NotImplementedError


def parse_act(html: str, url: str, snapshot_id: str) -> Document:
    """TODO (90 min) — extrage textul actului + metadatele.

    De extras:
      - titlul complet (tip act, număr, an): „Legea nr. 227/2015"
      - data publicării în Monitorul Oficial -> published_at
      - data intrării în vigoare (adesea diferită!) -> pune-o în text, e o
        sursă bogată de claims
      - forma: consolidată la ce dată, sau forma inițială
      - corpul articolelor, curat, fără navigație

    source_type = "law", source_tier = G2.

    Notează forma și data consolidării în `SnapshotEntry.notes`. E singura ta
    apărare când, peste două luni, cifra din lege nu mai corespunde.
    """
    raise NotImplementedError


ACTS_SHORTLIST: list[dict] = [
    # TODO (S3) — alege 20-30 de acte pentru care ai claims verificabile literal.
    # Sugestii de start, cu multe praguri numerice și date de intrare în vigoare:
    #   Codul fiscal (Legea 227/2015)
    #   Codul muncii (Legea 53/2003)
    #   Legea finanțelor publice locale (273/2006)
    #   Legea educației naționale
    # Pentru fiecare: {"url": ..., "label": ..., "form": "consolidata la YYYY-MM-DD"}
]
