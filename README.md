# RoFact — Romanian-Language Automated Fact-Checking

> A machine-learning system that takes a claim in Romanian, retrieves evidence from a mixed corpus of primary and media sources, and predicts whether the claim is **supported**, **refuted**, or **not verifiable** — while citing the passages it relied on.


> **🚧 Status: early development.** This repository documents the design and roadmap of the project. Code, dataset, and results are being built out incrementally. Nothing here should be read as a finished, evaluated system yet.

---

## What it does

Given a factual claim written in Romanian, RoFact returns one of:

| Label | Meaning |
|-------|---------|
| `SUPPORTED` | The claim is backed by the reference sources. |
| `REFUTED` | The claim is contradicted by the reference sources. |
| `NOT_ENOUGH_INFO` | There is not enough evidence for a verdict. |
| `MIXED` *(optional)* | The claim mixes correct and incorrect elements. |

Alongside the verdict, the system returns the **evidence passages used**, their **sources and publication dates**, a **short explanation**, a **confidence score**, and a **warning when sources disagree**.

RoFact is not an "oracle of truth." A verdict means:

> *"This is the conclusion supported by the reference corpus available at the time the dataset was built."*

The first version focuses on a deliberately narrow set of domains where primary sources are strong and structured: **economy, demography, public administration, legislation, and official statistics about Romania and the EU.**

---

## Why this project exists (the research question)

Most fact-checking datasets are built on clean, curated evidence. Reality is messier: official statistics sit next to news articles that repeat a claim without proof, paraphrase a source, use outdated numbers, omit context, or contradict the primary source outright.

The central experimental question RoFact is designed to answer is:

> **How much does a Romanian fact-checker's performance degrade when official sources are mixed with incomplete, repetitive, outdated, or contradictory media coverage?**

To study this, the corpus deliberately blends **primary/reference sources** with **realistic media "noise"**, and the system is evaluated across three scenarios: clean, moderate noise, and heavy noise.

---

## System architecture

```text
User claim
    ↓
Normalization + extraction of entities, numbers, dates
    ↓
Retriever  →  find candidate evidence passages
    ↓
Reranker   →  select the best passages
    ↓
Source type & quality analysis
    ↓
Verifier   →  SUPPORTS / REFUTES / NEI
    ↓
Evidence aggregation + confidence calibration
    ↓
Verdict + explanation + citations
```

Two models are trained and evaluated **separately**:

1. **Retriever** — finds the evidence (dense retrieval, benchmarked against a BM25 baseline).
2. **Verifier** — compares a claim to a passage and predicts their relation (fine-tuned multilingual encoder, e.g. XLM-RoBERTa).

---

## Ground-truth policy

Labels do **not** come from a language model or directly from a news article. They come from **primary or reference sources**, stored as fixed snapshots:

- **G1 — structured primary data:** [INS TEMPO Online](https://statistici.insse.ro/tempoins/?lang=en), [Eurostat](https://ec.europa.eu/eurostat/data/database), [data.gov.ro](https://data.gov.ro/), [Portalul Legislativ](https://legislatie.just.ro/).
- **G2 — official documents:** institutional reports, official communications, legal texts, budgets, methodologies.
- **G3 — documented fact-checks** (e.g. [Factual.ro](https://www.factual.ro/), [AFP Fact Check România](https://factcheck.afp.com/AFP-Romania)) — used only to *discover* claims and sources, never copied as labels.

**Core rule:** a claim gets its final label only from manually approved G1–G3 evidence. Media sources can influence retrieval difficulty, but never set the ground truth on their own.

Every document stores its **retrieval date** and a **content hash**, because some official databases update in place without historical versioning. All experiments therefore run on **fixed snapshots** for reproducibility.

### Two-axis passage annotation

Each media passage receives two independent labels — this separation is central to the project:

- **Textual relation to the claim:** `SUPPORTS` / `REFUTES` / `MENTIONS` / `IRRELEVANT`
- **Evidence quality:** `GOLD_PRIMARY` / `CORROBORATIVE` / `UNVERIFIED` / `MISLEADING` / `OUTDATED`

A news article can *textually support* a false claim — so it is not automatically marked `REFUTES` just because the official source shows the claim is false.

---

## Dataset

Three JSONL files (structure inspired by [FEVER](https://fever.ai/dataset/fever.html)):

- `claims.jsonl` — claims with label, topic, date, `family_id` (groups variants of the same claim), and gold evidence IDs.
- `documents.jsonl` — corpus documents with source type, tier (G1/G2/G3), publication date, retrieval date, and content hash.
- `claim_passage_pairs.jsonl` — claim–passage links with the two-axis annotation.

**Target size (individual project):** ~900 usable gold claims (balanced ~300 `SUPPORTED` / 300 `REFUTED` / 300 `NEI`) + 100 challenge claims, over a corpus of 5,000–15,000 passages. At least 20% of claims double-annotated; dedicated subsets for numeric, temporal, and contradictory-source cases.

Claims are built from three sources: ~40% real public claims (reformulated atomically), ~40% constructed from primary values (with controlled correct / refuted / NEI variants), ~20% hard cases requiring multiple sources. Synthetic claims may be *proposed* by an LLM but receive a label only after manual review.

---

## Planned repository structure

```text
rofact/
├── data/                # dataset snapshots (or download scripts) + data card
├── src/
│   ├── ingestion/       # source collection, snapshotting, passage segmentation
│   ├── retriever/       # BM25 baseline + dense retriever
│   ├── verifier/        # claim–evidence classifier
│   ├── pipeline/        # end-to-end orchestration + aggregation
│   └── evaluation/      # metrics for retriever, verifier, end-to-end
├── app/                 # demo (FastAPI backend + Streamlit/React frontend)
├── notebooks/           # exploration and error analysis
├── configs/             # experiment configs
├── docs/                # dataset card, model card, project spec
└── README.md
```

---

## Getting started

> Installation and usage instructions will be added as components land. Placeholder below.

```bash
git clone https://github.com/mmandragiu/rofact.git
cd rofact
pip install -r requirements.txt

# build the search index (WIP)
python -m src.ingestion.build_index

# run the demo (WIP)
uvicorn app.api:app --reload
```

---

## Evaluation

**Retriever:** Recall@{5,10,20}, MRR, nDCG, and % of cases where all required evidence was retrieved.

**Verifier:** macro-F1, per-class F1, confusion matrix, and calibration (Expected Calibration Error / Brier score).

**End-to-end:** a result counts as correct only if the verdict is right **and** the system cites at least one sufficient gold passage. Reported across three corpus scenarios:

| Scenario | Corpus |
|----------|--------|
| Clean | Reference sources only |
| Moderate noise | 1 gold passage per 5 media distractors |
| Heavy noise | 1 gold passage per 20 distractors + contradictory sources |

Indicative targets: Recall@10 ≥ 85%, verifier macro-F1 ≥ 75%, end-to-end macro-F1 ≥ 65%.

---

## Roadmap

- [ ] **Spec & annotation guidelines** — domains, labels, ground-truth policy, source registry.
- [ ] **Primary-source corpus** — snapshots from INS / Eurostat / data.gov.ro / legislation.
- [ ] **Mixed media corpus** — diverse sources, dedup, copy detection, source typing.
- [ ] **Gold set v0.1** — first 200–300 annotated claims + inter-annotator agreement.
- [ ] **Lexical baseline** — BM25 + logistic-regression verifier.
- [ ] **Dense retriever** — fine-tuning + hard-negative mining.
- [ ] **Verifier** — multilingual encoder fine-tuned on the three classes + calibration.
- [ ] **Noise & robustness** — difficulty curriculum, contradictory-source tests, ablations.
- [ ] **End-to-end pipeline** — retrieval → verification → aggregation → explanations.
- [ ] **Demo app** — evidence display, confidence scores, contradiction warnings.
- [ ] **Release** — dataset card, model card, reproducible scripts, report.

---

## Limitations & responsible use

- RoFact reflects **only** the reference corpus captured at dataset-build time; it does not know facts published later.
- It is a **research prototype**, not a production fact-checking service, and should not be used to make automated judgments about people or to label real published content.
- Source *type* is used for evidence rules and analysis — **not** to learn that "outlet X always tells the truth." The system must be able to answer `NOT_ENOUGH_INFO`.
- Media content in the corpus is used strictly for research; see the data card for licensing and source-usage details.

---

## Citation

If you reference this project, please cite:

```bibtex
@misc{rofact,
  title  = {RoFact: Romanian-Language Automated Fact-Checking},
  author = {Mandragiu, Mihai},
  year   = {2026},
  note   = {Work in progress},
  url    = {https://github.com/mmandragiu/rofact.git}
}
```

---

## License

Code is released under the **MIT License** (see `LICENSE`). Dataset licensing is handled separately in the data card, since it depends on the terms of each underlying source.

---

## Acknowledgements

Project designed as an independent research effort, with mentorship guidance. Built on open multilingual NLP models and Romanian/EU public data sources.
