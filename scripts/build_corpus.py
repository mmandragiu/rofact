"""CLI de construire a corpusului: ingest -> documente -> pasaje.

    python scripts/build_corpus.py --sources eurostat ins_tempo
    python scripts/build_corpus.py --sources all --snapshot 2026-07-21
    python scripts/build_corpus.py --segment-only        # re-segmentează fără re-descărcare

Separarea „ingest" / „segment" e intenționată: vei schimba strategia de
segmentare de câteva ori în S2–S4, iar re-descărcarea de fiecare dată e lentă,
nepoliticoasă față de surse și îți schimbă snapshotul fără motiv.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rofact import io  # noqa: E402
from rofact.ingest import base  # noqa: E402

SOURCES = ["eurostat", "ins_tempo", "datagov", "legislatie", "pdf_docs", "media"]


def run_ingest(source: str, snapshot_id: str):
    """TODO (30 min) — dispecer către modulul de ingest potrivit.

    Fiecare ramură întoarce (list[Document], list[SnapshotEntry]).
    Ține-le într-un acumulator; scrii o singură dată la final.
    """
    raise NotImplementedError


def main() -> int:
    ap = argparse.ArgumentParser(description="Construiește corpusul RoFact.")
    ap.add_argument("--sources", nargs="+", default=["eurostat"],
                    choices=SOURCES + ["all"])
    ap.add_argument("--snapshot", default=None,
                    help="snapshot_id (implicit: data de azi)")
    ap.add_argument("--segment-only", action="store_true",
                    help="re-segmentează documents.jsonl fără a re-descărca")
    args = ap.parse_args()

    io.ensure_dirs()
    snapshot_id = args.snapshot or base.today_snapshot_id()
    sources = SOURCES if "all" in args.sources else args.sources

    print(f"snapshot: {snapshot_id}")
    print(f"surse:    {', '.join(sources)}")

    # TODO (40 min):
    #   1. dacă nu --segment-only: pentru fiecare sursă, run_ingest(...);
    #      acumulează documente + entries
    #   2. io.write_jsonl(io.DOCUMENTS_PATH, documents)
    #   3. base.write_manifest(snapshot_id, entries)
    #   4. documents = io.read_jsonl(io.DOCUMENTS_PATH, Document)
    #   5. passages = passages.build_passages(documents)
    #   6. io.write_jsonl(io.PASSAGES_PATH, passages)
    #   7. afișează sumarul: documente/pasaje pe tier și pe source_type
    #   8. rulează validate_data la final (import, nu subprocess)
    raise NotImplementedError


if __name__ == "__main__":
    raise SystemExit(main())
