"""Validator de invarianți pentru datasetul RoFact.

Rulează-l DUPĂ FIECARE SESIUNE DE ADNOTARE:

    python scripts/validate_data.py
    python scripts/validate_data.py --strict     # avertismentele devin erori

Structura: fiecare verificare e o funcție `check_*` care întoarce o listă de
Issue. Patru sunt implementate ca exemplu; restul au TODO — completează-le tu.
Nu le lăsa pe mai târziu: verificarea de leakage (C5) e cea care te salvează de
rezultate umflate la S10.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rofact import io
from rofact.schemas import (
    Claim,
    ClaimPassagePair,
    Document,
    EvidenceQuality,
    Label,
    Passage,
    PerturbationType,
    Split,
    TextualRelation,
)

Severity = str  # "error" | "warning"


@dataclass
class Issue:
    severity: Severity
    check: str
    message: str

    def __str__(self) -> str:
        mark = "ERROR  " if self.severity == "error" else "WARN   "
        return f"{mark} [{self.check}] {self.message}"


@dataclass
class Dataset:
    documents: list[Document]
    passages: list[Passage]
    claims: list[Claim]
    pairs: list[ClaimPassagePair]

    @classmethod
    def load(cls) -> "Dataset":
        return cls(
            documents=io.read_jsonl(io.DOCUMENTS_PATH, Document),
            passages=io.read_jsonl(io.PASSAGES_PATH, Passage),
            claims=io.read_jsonl(io.CLAIMS_PATH, Claim),
            pairs=io.read_jsonl(io.PAIRS_PATH, ClaimPassagePair),
        )


# C1 - unicitatea identificatorilor [DONE]

def check_unique_ids(ds: Dataset) -> list[Issue]:
    issues: list[Issue] = []
    for name, ids in [
        ("documents", [d.document_id for d in ds.documents]),
        ("passages", [p.passage_id for p in ds.passages]),
        ("claims", [c.claim_id for c in ds.claims]),
    ]:
        dupes = [i for i, n in Counter(ids).items() if n > 1]
        if dupes:
            issues.append(Issue("error", "C1",
                                f"{name}: {len(dupes)} ID-uri duplicate, ex. {dupes[:5]}"))

    pair_keys = [(p.claim_id, p.passage_id) for p in ds.pairs]
    dupes = [k for k, n in Counter(pair_keys).items() if n > 1]
    if dupes:
        issues.append(Issue("error", "C1",
                            f"claim_passage_pairs: {len(dupes)} perechi duplicate, ex. {dupes[:3]}"))
    return issues



# C2 - integritatea referențială [DONE]

def check_referential_integrity(ds: Dataset) -> list[Issue]:
    issues: list[Issue] = []
    doc_ids = {d.document_id for d in ds.documents}
    passage_ids = {p.passage_id for p in ds.passages}
    claim_ids = {c.claim_id for c in ds.claims}

    orphan_passages = [p.passage_id for p in ds.passages if p.document_id not in doc_ids]
    if orphan_passages:
        issues.append(Issue("error", "C2",
                            f"{len(orphan_passages)} pasaje fără document, ex. {orphan_passages[:5]}"))

    for c in ds.claims:
        missing = [g for g in c.gold_evidence_ids if g not in passage_ids]
        if missing:
            issues.append(Issue("error", "C2",
                                f"{c.claim_id}: gold_evidence_ids inexistente: {missing}"))

    for p in ds.pairs:
        if p.claim_id not in claim_ids:
            issues.append(Issue("error", "C2", f"pereche cu claim inexistent: {p.claim_id}"))
        if p.passage_id not in passage_ids:
            issues.append(Issue("error", "C2", f"pereche cu pasaj inexistent: {p.passage_id}"))
    return issues



# C3 - coerența etichetă / dovezi [DONE]

def check_label_evidence_consistency(ds: Dataset) -> list[Issue]:
    """Invarianții de bază sunt deja în schema Pydantic; aici verificăm
    consistența ÎNTRE fișiere, ceea ce schema singură nu poate face."""
    issues: list[Issue] = []
    pairs_by_claim: dict[str, list[ClaimPassagePair]] = defaultdict(list)
    for p in ds.pairs:
        pairs_by_claim[p.claim_id].append(p)

    for c in ds.claims:
        gold_in_pairs = {p.passage_id for p in pairs_by_claim[c.claim_id] if p.is_gold}
        gold_in_claim = set(c.gold_evidence_ids)

        if gold_in_claim - gold_in_pairs:
            issues.append(Issue("error", "C3",
                                f"{c.claim_id}: pasaje în gold_evidence_ids fără pereche "
                                f"is_gold=True: {sorted(gold_in_claim - gold_in_pairs)}"))
        if gold_in_pairs - gold_in_claim:
            issues.append(Issue("error", "C3",
                                f"{c.claim_id}: perechi is_gold=True lipsă din "
                                f"gold_evidence_ids: {sorted(gold_in_pairs - gold_in_claim)}"))

        # O afirmație REFUTED are nevoie de un pasaj care chiar o contrazice.
        if c.label == Label.REFUTED:
            has_refuting_gold = any(
                p.is_gold and p.textual_relation == TextualRelation.REFUTES
                for p in pairs_by_claim[c.claim_id]
            )
            if not has_refuting_gold:
                issues.append(Issue("error", "C3",
                                    f"{c.claim_id}: REFUTED fără niciun pasaj gold cu "
                                    "textual_relation=REFUTES"))

        if c.label == Label.SUPPORTED:
            has_supporting_gold = any(
                p.is_gold and p.textual_relation == TextualRelation.SUPPORTS
                for p in pairs_by_claim[c.claim_id]
            )
            if not has_supporting_gold:
                issues.append(Issue("error", "C3",
                                    f"{c.claim_id}: SUPPORTED fără niciun pasaj gold cu "
                                    "textual_relation=SUPPORTS"))
    return issues



# C4 - sursele media nu pot fi ground truth [DONE]

def check_media_never_gold(ds: Dataset) -> list[Issue]:
    """Regula centrală a proiectului. Dacă pică asta, datasetul e compromis."""
    issues: list[Issue] = []
    tier_by_passage = {}
    tier_by_doc = {d.document_id: d.source_tier for d in ds.documents}
    for p in ds.passages:
        if p.document_id in tier_by_doc:
            tier_by_passage[p.passage_id] = tier_by_doc[p.document_id]

    for pair in ds.pairs:
        tier = tier_by_passage.get(pair.passage_id)
        if tier is None:
            continue
        if pair.is_gold and tier.value in ("MEDIA", "G3"):
            issues.append(Issue("error", "C4",
                                f"{pair.claim_id}/{pair.passage_id}: pasaj {tier.value} marcat "
                                "ca gold. Media și G3 nu stabilesc niciodată eticheta."))
        if pair.evidence_quality == EvidenceQuality.GOLD_PRIMARY and tier.value not in ("G1", "G2"):
            issues.append(Issue("error", "C4",
                                f"{pair.claim_id}/{pair.passage_id}: GOLD_PRIMARY pe o sursă "
                                f"{tier.value}."))
    return issues


# C5 - leakage prin family_id [DONE]

def check_family_split_leakage(ds: Dataset) -> list[Issue]:
    issues : list[Issue] = []
    claims_by_family : dict[str, list[tuple[str, str]]] = defaultdict(list)

    for claim in ds.claims:
        if claim.split is None:
            continue
        claims_by_family[claim.family_id].append((claim.split.value, claim.claim_id))

    for family_id, entries in claims_by_family.items():
        distinct_splits = {split for split, _ in entries}
        if len(distinct_splits) > 1:
            splits_spread = ", ".join(f"{claim_id} = {split}" for split, claim_id in sorted(entries))
            issues.append(Issue("error", "C5", f"family_id '{family_id}' e împrăștiat în {len(distinct_splits)} split-uri : {splits_spread}"))
    return issues


# C6 — cvasi-duplicate între claims [TODO]

def check_near_duplicate_claims(ds: Dataset, threshold: float = 0.9) -> list[Issue]:
    """TODO — două afirmații aproape identice în split-uri diferite = leakage
    care scapă de C5 (pentru că au family_id diferit din greșeală).

    De implementat:
      1. normalizează textul (io.normalize_text + lowercase);
      2. calculează similaritatea pe shingles de 3 cuvinte (Jaccard) sau
         folosește datasketch.MinHashLSH — la 650 de claims O(n²) merge, dar
         MinHash e mai curat și îl refolosești la dedup de documente în S4;
      3. perechile peste `threshold` cu family_id diferit -> warning;
      4. aceleași perechi în split-uri diferite -> error.
    """
    raise NotImplementedError("C6: implementează detecția de cvasi-duplicate")


# C7 - echilibrul claselor și al domeniilor [TODO]

def check_class_balance(ds: Dataset, tolerance: float = 0.10) -> list[Issue]:
    """TODO — clasele trebuie să fie în ±10% de la echilibru (fără MIXED, care
    e doar în challenge).

    De implementat:
      1. numără SUPPORTED / REFUTED / NOT_ENOUGH_INFO pe split-urile
         train+val+test;
      2. dacă vreo clasă deviază cu >`tolerance` de la 1/3 -> warning;
      3. la fel pe `topic`, față de țintele din RoFact_plan_executie.md
         (economie 180, demografie 150, statistici 120, administrație 110,
         legislație 90) -> warning cu diferența;
      4. verifică și echilibrul PE SPLIT, nu doar global — un test set
         dezechilibrat face macro-F1 instabil.
    """
    raise NotImplementedError("C7: implementează verificarea de echilibru")


# C8 - artefacte de perturbare [TODO]

def check_perturbation_diversity(ds: Dataset, max_share: float = 0.40) -> list[Issue]:
    """TODO — dacă >40% din afirmațiile `constructed` folosesc aceeași
    perturbare, modelul învață șablonul, nu faptul.

    De implementat:
      1. filtrează claims cu creation_method=CONSTRUCTED și
         perturbation_type != NONE;
      2. Counter pe perturbation_type;
      3. orice tip peste `max_share` -> warning cu procentul;
      4. bonus util: verifică diversitatea și ÎN INTERIORUL clasei REFUTED
         separat — acolo se concentrează de obicei artefactul.
    """
    raise NotImplementedError("C8: implementează verificarea de diversitate")


# C9 - acoperirea țintelor de dataset [TODO]

def check_coverage_targets(ds: Dataset) -> list[Issue]:
    """TODO — țintele din spec, verificate automat ca să nu descoperi la S12
    că îți lipsesc.

    Ținte (warning dacă nu sunt atinse):
      - >= 200 claims cu has_number=True
      - >= 150 claims cu requires_multi_evidence=True
      - >= 100 claims cu has_date=True
      - >=  80 claims cu has_negation=True sau has_comparison=True
      - >=  80 claims cu cel puțin un pasaj MEDIA care are
             textual_relation=SUPPORTS dar claim.label=REFUTED
             (cazurile de „media susține o afirmație falsă" — categoria cea mai
              valoroasă din tot datasetul)
      - >= 20% din claims cu second_annotator_id != None
    """
    raise NotImplementedError("C9: implementează verificarea de acoperire")


# C10 - licențe și snapshot-uri [TODO]

def check_licenses_and_snapshots(ds: Dataset) -> list[Issue]:
    """TODO — igienă de date, ieftin de verificat, scump de reparat la S12.

    De implementat:
      1. niciun Document cu source_tier G1/G2 nu are license="unknown" -> error;
      2. fiecare document are snapshot_id nevid și un manifest corespunzător în
         data/snapshots/manifests/{snapshot_id}.json -> error dacă lipsește;
      3. published_at <= retrieved_at -> error;
      4. pentru fiecare claim, TOATE pasajele gold provin din documente cu
         published_at <= claim_date (o dovadă publicată după data afirmației e
         suspectă) -> warning, cu explicație în raport.
    """
    raise NotImplementedError("C10: implementează verificarea de licențe/snapshot")



CHECKS = [
    ("C1  unicitate ID-uri", check_unique_ids),
    ("C2  integritate referențială", check_referential_integrity),
    ("C3  coerență etichetă/dovezi", check_label_evidence_consistency),
    ("C4  media niciodată gold", check_media_never_gold),
    ("C5  leakage family_id", check_family_split_leakage),
    ("C6  cvasi-duplicate", check_near_duplicate_claims),
    ("C7  echilibru clase", check_class_balance),
    ("C8  diversitate perturbări", check_perturbation_diversity),
    ("C9  acoperire ținte", check_coverage_targets),
    ("C10 licențe & snapshot", check_licenses_and_snapshots),
]


def summarize(ds: Dataset) -> str:
    by_label = Counter(c.label.value for c in ds.claims)
    by_topic = Counter(c.topic.value for c in ds.claims)
    by_split = Counter(c.split.value if c.split else "—" for c in ds.claims)
    by_tier = Counter(d.source_tier.value for d in ds.documents)
    lines = [
        f"documente: {len(ds.documents):>6}   {dict(by_tier)}",
        f"pasaje:    {len(ds.passages):>6}",
        f"claims:    {len(ds.claims):>6}   {dict(by_label)}",
        f"           {'':>6}   {dict(by_topic)}",
        f"           {'':>6}   split: {dict(by_split)}",
        f"perechi:   {len(ds.pairs):>6}",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Validează datasetul RoFact.")
    ap.add_argument("--strict", action="store_true",
                    help="tratează avertismentele ca erori")
    ap.add_argument("--skip-todo", action="store_true", default=True,
                    help="ignoră verificările neimplementate (implicit: da)")
    args = ap.parse_args()

    io.ensure_dirs()
    try:
        ds = Dataset.load()
    except ValueError as exc:
        print(f"ERROR  Nu pot încărca datasetul: {exc}")
        return 2

    print(summarize(ds))
    print("-" * 72)

    all_issues: list[Issue] = []
    not_implemented: list[str] = []

    for name, fn in CHECKS:
        try:
            issues = fn(ds)
        except NotImplementedError:
            not_implemented.append(name)
            continue
        status = "OK" if not issues else f"{len(issues)} probleme"
        print(f"{name:<34} {status}")
        all_issues.extend(issues)

    if not_implemented:
        print("-" * 72)
        print("NEIMPLEMENTATE (completează-le):")
        for name in not_implemented:
            print(f"  - {name}")

    errors = [i for i in all_issues if i.severity == "error"]
    warnings = [i for i in all_issues if i.severity == "warning"]

    if all_issues:
        print("-" * 72)
        for issue in all_issues[:80]:
            print(issue)
        if len(all_issues) > 80:
            print(f"... și încă {len(all_issues) - 80}")

    print("-" * 72)
    print(f"{len(errors)} erori, {len(warnings)} avertismente")
    if errors or (args.strict and warnings):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
