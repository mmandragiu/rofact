"""Build the corpus: ingest -> documents -> passages.

    python scripts/build_corpus.py --sources eurostat
    python scripts/build_corpus.py --sources all --snapshot 2026-10-20
    python scripts/build_corpus.py --segment-only     # re-segment, no downloading

Splitting "ingest" from "segment" is deliberate: the segmentation strategy will
change several times during S2-S4, and re-downloading each time is slow, rude to
the sources, and silently changes the snapshot for no reason.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rofact import io
from rofact.ingest import base
from rofact.passages import build_passages
from rofact.schemas import Document, Passage, SnapshotEntry

SOURCES = ["eurostat", "ins_tempo", "datagov", "legislatie", "pdf_docs", "media"]

# Sources that are not automated are listed here so the script says WHY instead of
# failing with an import error. Reasons come from docs/source_registry.md.
NOT_AUTOMATED = {
    "datagov": "CKAN dă doar metadate; datele sunt XLSX/PDF, câte un layout per "
               "instituție. Decizie de luat la S3 (vezi source_registry.md).",
    "pdf_docs": "Rapoarte BNR / Ministerul Finanțelor, de implementat la S3.",
    "media": "Corpusul de presă, S4.",
}


# Which source a stored document came from. The domain is recorded on every
# Document, so it survives a round trip through documents.jsonl.
DOMAIN_TO_SOURCE = {
    "ec.europa.eu": "eurostat",
    "insse.ro": "ins_tempo",
    "legislatie.just.ro": "legislatie",
}


def source_of(document: Document) -> str:
    return DOMAIN_TO_SOURCE.get(document.domain or "", document.domain or "?")


def run_ingest(source: str, snapshot_id: str) -> tuple[list[Document], list[SnapshotEntry]]:
    """Dispatch to the right ingest module."""
    if source == "eurostat":
        from rofact.ingest import eurostat
        return eurostat.ingest(snapshot_id)

    if source == "ins_tempo":
        from rofact.ingest import ins_tempo
        return ins_tempo.ingest(snapshot_id)

    if source == "legislatie":
        from rofact.ingest import legislatie
        return legislatie.ingest(snapshot_id)

    if source in NOT_AUTOMATED:
        raise NotImplementedError(f"{source}: {NOT_AUTOMATED[source]}")
    raise ValueError(f"sursă necunoscută: {source}")


def summarize(documents: list[Document], passages: list[Passage]) -> str:
    """What the corpus looks like now — the numbers that go into the data card."""
    by_doc = {d.document_id: d for d in documents}
    lines = [
        f"documente: {len(documents)}",
        f"  pe tier:        {dict(Counter(d.source_tier.value for d in documents))}",
        f"  pe source_type: {dict(Counter(d.source_type for d in documents))}",
        f"pasaje: {len(passages)}",
        f"  verbalizate:    {sum(p.is_verbalized for p in passages)}",
        f"  pe șablon:      {dict(Counter(p.template_id or '—' for p in passages))}",
    ]
    # Target: 10-13k passages, of which only 20-30% official. The rest must be
    # media, or the noise experiment has nothing to measure.
    official = sum(by_doc[p.document_id].source_tier.value in ("G1", "G2")
                   for p in passages if p.document_id in by_doc)
    if passages:
        lines.append(f"  din care G1/G2: {official} ({official / len(passages):.0%}) "
                     f"— țintă finală 20–30% din 10.000–13.000")
    return "\n".join(lines)


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

    if args.segment_only:
        print("re-segmentez din documents.jsonl, fără descărcare")
    else:
        print(f"snapshot: {snapshot_id}")
        print(f"surse:    {', '.join(sources)}\n")

        documents: list[Document] = []
        entries: list[SnapshotEntry] = []
        failed: list[str] = []
        refreshed: set[str] = set()
        for source in sources:
            try:
                docs, source_entries = run_ingest(source, snapshot_id)
            except NotImplementedError as exc:
                print(f"  — {exc}")
                continue
            except (RuntimeError, OSError) as exc:
                # A source being temporarily unreachable must not kill the whole
                # build: the sources that did answer are still worth writing.
                print(f"  ✗ {source}: {exc}")
                failed.append(source)
                continue
            print(f"  ✓ {source}: {len(docs)} documente, "
                  f"{sum(e.n_records or 0 for e in source_entries)} înregistrări")
            documents += docs
            entries += source_entries
            refreshed.add(source)

        if not documents:
            print("\nNiciun document descărcat. Nu suprascriu documents.jsonl.")
            return 1

        # Keep what was there for every source NOT refreshed in this run — failed or
        # simply not asked for. A build used to rewrite the corpus from scratch, so
        # when the Ministry of Justice's service returned HTTP 500 the whole
        # legislative corpus vanished (1,793 -> 1,025 passages). Kept documents
        # carry their own snapshot_id, so they still point at the manifest they
        # were fetched under.
        kept = [d for d in io.read_jsonl(io.DOCUMENTS_PATH, Document)
                if source_of(d) not in refreshed]
        if kept:
            by_source = Counter(source_of(d) for d in kept)
            print("  ↺ păstrate din build-ul anterior: "
                  + ", ".join(f"{s} ({n} documente)" for s, n in sorted(by_source.items())))
        documents = kept + documents

        io.write_jsonl(io.DOCUMENTS_PATH, documents)
        manifest = base.write_manifest(snapshot_id, entries)
        print(f"\nscris {io.DOCUMENTS_PATH.name} și {manifest.name}")

    # Read the documents back through the schema, so segmentation always runs on
    # validated data — the same path a later session would take.
    documents = io.read_jsonl(io.DOCUMENTS_PATH, Document)
    if not documents:
        print(f"{io.DOCUMENTS_PATH} e gol — rulează întâi fără --segment-only.")
        return 1

    passages = build_passages(documents)
    io.write_jsonl(io.PASSAGES_PATH, passages)
    print(f"scris {io.PASSAGES_PATH.name}\n")
    print(summarize(documents, passages))

    # The validator runs on every build, not only after annotating: a corpus that
    # breaks an invariant should be caught before anything is annotated on top of it.
    print("\n" + "-" * 72)
    import validate_data

    dataset = validate_data.Dataset.load()
    issues = []
    for _name, check in validate_data.CHECKS:
        try:
            issues += check(dataset)
        except NotImplementedError:
            continue
    errors = [i for i in issues if i.severity == "error"]
    for issue in issues[:20]:
        print(issue)
    print(f"validator: {len(errors)} erori, {len(issues) - len(errors)} avertismente")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
