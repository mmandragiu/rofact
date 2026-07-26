"""Utilitare de I/O: JSONL tipizat, hashing, căi de proiect, snapshot-uri.

Modul complet — nu are TODO-uri. Îl folosești din toate celelalte module.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import date
from pathlib import Path
from typing import Iterable, Iterator, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

# --------------------------------------------------------------------------- #
# Căi                                                                          #
# --------------------------------------------------------------------------- #

ROOT = Path(__file__).resolve().parents[2]

DATA = ROOT / "data"
RAW = DATA / "raw"
SNAPSHOTS = DATA / "snapshots"
MANIFESTS = SNAPSHOTS / "manifests"
PROCESSED = DATA / "processed"
ANNOTATIONS = DATA / "annotations"
CONFIGS = ROOT / "configs"
RESULTS = ROOT / "results"

DOCUMENTS_PATH = PROCESSED / "documents.jsonl"
PASSAGES_PATH = PROCESSED / "passages.jsonl"
CLAIMS_PATH = ANNOTATIONS / "claims.jsonl"
PAIRS_PATH = ANNOTATIONS / "claim_passage_pairs.jsonl"


def ensure_dirs() -> None:
    for p in (RAW, SNAPSHOTS, MANIFESTS, PROCESSED, ANNOTATIONS, RESULTS):
        p.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------- #
# Normalizare + hashing                                                        #
# --------------------------------------------------------------------------- #

_WS = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """Normalizare stabilă, folosită ÎNAINTE de hashing și de segmentare.

    Important: hash-ul trebuie calculat pe textul normalizat, altfel o simplă
    schimbare de spațiere pe site-ul sursă îți invalidează snapshot-ul.

    Atenție la diacritice: în română circulă două variante ale lui ș/ț
    (cu sedilă U+015F/U+0163 vs. cu virgulă U+0219/U+021B). NFC singur nu le
    unifică, deci le mapăm explicit la varianta cu virgulă (cea corectă).
    """
    text = unicodedata.normalize("NFC", text)
    text = (text
            .replace("ş", "ș").replace("Ş", "Ș")   # ş -> ș
            .replace("ţ", "ț").replace("Ţ", "Ț")   # ţ -> ț
            .replace(" ", " ")                                     # nbsp
            .replace("’", "'").replace("‘", "'")
            .replace("“", '"').replace("”", '"')
            .replace("–", "-").replace("—", "-"))
    return _WS.sub(" ", text).strip()


def sha256_text(text: str, *, normalize: bool = True) -> str:
    payload = normalize_text(text) if normalize else text
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def stable_id(prefix: str, *parts: str, length: int = 12) -> str:
    """ID determinist și reproductibil: același input -> același ID.

    Folosește-l peste tot. Dacă ID-urile depind de ordinea de procesare, o
    re-rulare a ingest-ului îți rupe toate adnotările.

    >>> stable_id("ins", "POP105A", "2023")
    'ins_...'
    """
    digest = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:length]
    return f"{prefix}_{digest}"


# --------------------------------------------------------------------------- #
# JSONL tipizat                                                                #
# --------------------------------------------------------------------------- #

def _json_default(o):
    if isinstance(o, date):
        return o.isoformat()
    raise TypeError(f"Nu pot serializa {type(o)}")


def write_jsonl(path: Path, items: Iterable[BaseModel], *, append: bool = False) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    n = 0
    with open(path, mode, encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item.model_dump(mode="json"), ensure_ascii=False,
                               default=_json_default) + "\n")
            n += 1
    return n


def read_jsonl(path: Path, model: type[T]) -> list[T]:
    """Citește și validează. Ridică eroare cu numărul liniei — nu ghici unde e problema."""
    out: list[T] = []
    if not path.exists():
        return out
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                out.append(model.model_validate_json(line))
            except Exception as exc:
                raise ValueError(f"{path.name}:{lineno} — {exc}") from exc
    return out


def iter_jsonl_raw(path: Path) -> Iterator[dict]:
    """Citire fără validare — pentru inspecție rapidă sau migrări de schemă."""
    if not path.exists():
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def append_jsonl(path: Path, item: BaseModel) -> None:
    """Scriere incrementală — folosită de unealta de adnotare, ca să nu pierzi lucru."""
    write_jsonl(path, [item], append=True)


__all__ = [
    "ROOT", "DATA", "RAW", "SNAPSHOTS", "MANIFESTS", "PROCESSED", "ANNOTATIONS",
    "CONFIGS", "RESULTS",
    "DOCUMENTS_PATH", "PASSAGES_PATH", "CLAIMS_PATH", "PAIRS_PATH",
    "ensure_dirs", "normalize_text", "sha256_text", "sha256_file", "stable_id",
    "write_jsonl", "read_jsonl", "iter_jsonl_raw", "append_jsonl",
]
