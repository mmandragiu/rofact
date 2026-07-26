"""Conectori de ingest, unul per sursă.

Fiecare modul expune o funcție `fetch_*` care:
  1. descarcă datele brute,
  2. le salvează în data/snapshots/{snapshot_id}/,
  3. întoarce (list[Document], list[SnapshotEntry]).

Segmentarea în pasaje NU se face aici — e treaba lui rofact.passages.
Separarea contează: poți re-segmenta fără să re-descarci.
"""
