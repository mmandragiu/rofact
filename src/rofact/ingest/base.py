"""Infrastructură comună de ingest: snapshot-uri, HTTP politicos, manifest.

Modul aproape complet — două TODO-uri mici marcate mai jos.
"""

from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path
from typing import Any

import requests

from rofact import io
from rofact.schemas import SnapshotEntry, SnapshotManifest

USER_AGENT = "RoFact-research/0.1 (proiect studentesc; contact: <pune-ti-emailul>)"

DEFAULT_TIMEOUT = 30
DEFAULT_DELAY = 1.5


# --------------------------------------------------------------------------- #
# Snapshot                                                                     #
# --------------------------------------------------------------------------- #

def today_snapshot_id() -> str:
    return date.today().isoformat()


def snapshot_dir(snapshot_id: str) -> Path:
    d = io.SNAPSHOTS / snapshot_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_raw(snapshot_id: str, source_id: str, resource: str,
             payload: str | bytes, ext: str = "json") -> Path:
    """Salvează răspunsul brut, exact cum a venit. Nu-l normaliza aici.

    Textul brut e proba ta: dacă peste trei luni cifrele diferă, el arată ce ai
    descărcat efectiv.
    """
    d = snapshot_dir(snapshot_id) / source_id
    d.mkdir(parents=True, exist_ok=True)
    safe = resource.replace("/", "_").replace(":", "_")
    path = d / f"{safe}.{ext}"
    mode, enc = ("wb", None) if isinstance(payload, bytes) else ("w", "utf-8")
    with open(path, mode, encoding=enc) as f:
        f.write(payload)
    return path


def polite_get(url: str, *, params: dict[str, Any] | None = None,
               delay: float = DEFAULT_DELAY, timeout: int = DEFAULT_TIMEOUT,
               session: requests.Session | None = None) -> requests.Response:
    """GET cu User-Agent identificabil și pauză după cerere.

    Pauza e DUPĂ, nu înainte: astfel prima cerere e instantanee, iar rafalele
    sunt limitate corect.
    """
    s = session or requests
    resp = s.get(url, params=params, timeout=timeout,
                 headers={"User-Agent": USER_AGENT})
    time.sleep(delay)
    resp.raise_for_status()
    return resp


def make_entry(source_id: str, resource: str, url: str, raw_path: Path,
               n_records: int | None = None, notes: str | None = None) -> SnapshotEntry:
    return SnapshotEntry(
        source_id=source_id,
        resource=resource,
        url=url,
        retrieved_at=date.today(),
        raw_path=str(raw_path.relative_to(io.ROOT)).replace("\\", "/"),
        content_hash=io.sha256_file(raw_path),
        n_records=n_records,
        notes=notes,
    )


def write_manifest(snapshot_id: str, entries: list[SnapshotEntry]) -> Path:
    """Scrie/actualizează manifestul. Se COMITE în git."""
    io.MANIFESTS.mkdir(parents=True, exist_ok=True)
    path = io.MANIFESTS / f"{snapshot_id}.json"

    existing: dict[tuple[str, str], SnapshotEntry] = {}
    if path.exists():
        prev = SnapshotManifest.model_validate_json(path.read_text(encoding="utf-8"))
        existing = {(e.source_id, e.resource): e for e in prev.entries}

    for e in entries:
        existing[(e.source_id, e.resource)] = e

    manifest = SnapshotManifest(
        snapshot_id=snapshot_id,
        created_at=date.today(),
        entries=sorted(existing.values(), key=lambda e: (e.source_id, e.resource)),
    )
    path.write_text(
        json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def load_sources_config() -> dict[str, Any]:
    """TODO (10 min) — încarcă configs/sources.yaml cu PyYAML și întoarce dict-ul.

    Adaugă o verificare: dacă o sursă G1/G2 are `license_status: to_verify`,
    emite un warning la import. Sursele neverificate nu trebuie să ajungă
    tăcut în dataset.
    """
    raise NotImplementedError


def check_robots(base_url: str, path: str = "/") -> bool:
    """TODO (20 min) — verifică robots.txt cu urllib.robotparser.

    Semnătură sugerată: întoarce True dacă USER_AGENT are voie pe `path`.
    Apeleaz-o din legislatie.py și media.py ÎNAINTE de primul request.
    Pentru API-uri publice (Eurostat, TEMPO, CKAN) nu e necesară.
    """
    raise NotImplementedError
