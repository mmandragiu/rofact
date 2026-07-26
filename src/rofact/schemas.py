"""Schemele de date ale proiectului RoFact.

Acest modul este *definitional*: schimbarea lui invalidează adnotările deja făcute.
Dacă trebuie să-l modifici după S5, incrementează SCHEMA_VERSION și notează migrarea
în docs/journal.md.

Cele trei fișiere ale datasetului:
    data/processed/documents.jsonl            -> Document
    data/processed/passages.jsonl             -> Passage
    data/annotations/claims.jsonl             -> Claim
    data/annotations/claim_passage_pairs.jsonl -> ClaimPassagePair
"""

from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = "1.0.0"


# --------------------------------------------------------------------------- #
# Enumerări                                                                    #
# --------------------------------------------------------------------------- #

class Label(str, Enum):
    """Verdictul asociat unei afirmații.

    MIXED apare EXCLUSIV în split-ul `challenge`. Nu este a patra clasă de
    antrenare — vezi docs/dataset_spec.md, secțiunea „De ce MIXED nu se antrenează".
    """

    SUPPORTED = "SUPPORTED"
    REFUTED = "REFUTED"
    NOT_ENOUGH_INFO = "NOT_ENOUGH_INFO"
    MIXED = "MIXED"


class Topic(str, Enum):
    ECONOMIE = "economie"
    DEMOGRAFIE = "demografie"
    STATISTICI_RO_UE = "statistici_ro_ue"
    ADMINISTRATIE_PUBLICA = "administratie_publica"
    LEGISLATIE = "legislatie"


class SourceTier(str, Enum):
    """Nivelul de autoritate al sursei. Determină dreptul de a stabili eticheta."""

    G1 = "G1"        # date primare structurate: INS TEMPO, Eurostat, data.gov.ro
    G2 = "G2"        # documente oficiale: rapoarte, comunicate, legi, metodologii
    G3 = "G3"        # fact-check documentat: folosit pentru DESCOPERIRE, nu ca etichetă
    MEDIA = "MEDIA"  # presă și alte surse secundare — niciodată ground truth


class TextualRelation(str, Enum):
    """Ce face pasajul FAȚĂ DE TEXTUL afirmației.

    ATENȚIE: aceasta NU este eticheta afirmației. Un pasaj media poate avea
    SUPPORTS pentru o afirmație al cărei `label` este REFUTED. Asta e corect
    și intenționat.
    """

    SUPPORTS = "SUPPORTS"
    REFUTES = "REFUTES"
    MENTIONS = "MENTIONS"      # aduce afirmația în discuție fără s-o dovedească
    IRRELEVANT = "IRRELEVANT"


class EvidenceQuality(str, Enum):
    """Cât de bună e dovada, independent de ce spune ea."""

    GOLD_PRIMARY = "GOLD_PRIMARY"    # sursă primară, suficientă singură
    CORROBORATIVE = "CORROBORATIVE"  # confirmă corect, dar nu e primară
    UNVERIFIED = "UNVERIFIED"        # afirmă fără a proba
    MISLEADING = "MISLEADING"        # induce în eroare (context omis, cifră scoasă din context)
    OUTDATED = "OUTDATED"            # corect la vremea lui, greșit pentru `claim_date`


class CreationMethod(str, Enum):
    REAL_CLAIM = "real_claim"    # afirmație publică reală, reformulată atomic
    CONSTRUCTED = "constructed"  # derivată dintr-o valoare primară
    HARD = "hard"                # multi-evidence / comparativ / dependent de dată


class PerturbationType(str, Enum):
    """Cum a fost derivată o afirmație `constructed` din valoarea originală.

    Obligatoriu pentru creation_method=CONSTRUCTED. Validatorul dă alertă dacă
    o singură valoare depășește 40% — altfel modelul învață artefactul, nu faptul.
    """

    NONE = "none"                          # varianta corectă, nemodificată
    YEAR_SHIFT = "year_shift"
    VALUE_SHIFT = "value_shift"
    COUNTRY_SWAP = "country_swap"
    COMPARISON_FLIP = "comparison_flip"
    NEGATION = "negation"
    ABSOLUTE_VS_PERCENT = "absolute_vs_percent"
    ENTITY_SWAP = "entity_swap"            # indicator/instituție confundată
    SCOPE_SHIFT = "scope_shift"            # național vs. regional, rezident vs. domiciliu
    UNIT_SWAP = "unit_swap"                # lei vs. euro, mii vs. milioane


class NegativeType(str, Enum):
    """De ce un pasaj NU e dovadă bună — folosit la hard-negative mining."""

    REPEATS_CLAIM_WITHOUT_EVIDENCE = "repeats_claim_without_evidence"
    WRONG_YEAR = "wrong_year"
    WRONG_COUNTRY = "wrong_country"
    WRONG_ENTITY = "wrong_entity"
    WRONG_SCOPE = "wrong_scope"
    TOPICALLY_CLOSE_NO_EVIDENCE = "topically_close_no_evidence"
    OPINION = "opinion"
    OUTDATED_VALUE = "outdated_value"


class Split(str, Enum):
    TRAIN = "train"
    VAL = "val"
    TEST = "test"
    CHALLENGE = "challenge"


# --------------------------------------------------------------------------- #
# Corpus                                                                       #
# --------------------------------------------------------------------------- #

class Document(BaseModel):
    """Un document din corpus, într-un snapshot fix."""

    model_config = ConfigDict(extra="forbid")

    document_id: str
    source_url: str
    title: str
    source_type: str            # ex. "official_statistics", "news_agency", "law", "report"
    source_tier: SourceTier
    domain: str | None = None   # domeniul publicației, ex. "insse.ro" — util pentru dedup
    published_at: date | None
    retrieved_at: date
    snapshot_id: str            # ex. "2026-07-21" — leagă documentul de manifest
    content_hash: str           # sha256 al textului normalizat
    license: str                # vezi configs/sources.yaml; "unknown" e INTERZIS la G1/G2
    text: str

    @field_validator("content_hash")
    @classmethod
    def _hash_looks_like_sha256(cls, v: str) -> str:
        if len(v) != 64 or not all(c in "0123456789abcdef" for c in v.lower()):
            raise ValueError("content_hash trebuie să fie un sha256 hex de 64 de caractere")
        return v.lower()


class Passage(BaseModel):
    """Unitatea de regăsire. Retriever-ul caută pasaje, nu documente."""

    model_config = ConfigDict(extra="forbid")

    passage_id: str
    document_id: str
    text: str
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    section: str | None = None       # ex. "Art. 12" pentru legislație, "Tabel 3" pentru rapoarte

    # Pentru pasaje generate din tabele (vezi passages.verbalize_table):
    is_verbalized: bool = False
    template_id: str | None = None   # ca să poți verifica că nu ai un singur șablon

    @model_validator(mode="after")
    def _offsets_coherent(self):
        if self.char_end <= self.char_start:
            raise ValueError(f"{self.passage_id}: char_end trebuie > char_start")
        return self


# --------------------------------------------------------------------------- #
# Adnotări                                                                     #
# --------------------------------------------------------------------------- #

class Claim(BaseModel):
    """O afirmație etichetată.

    Reguli invariante (verificate în scripts/validate_data.py):
      - NOT_ENOUGH_INFO  => gold_evidence_ids este gol
      - SUPPORTED/REFUTED => cel puțin un gold cu GOLD_PRIMARY sau CORROBORATIVE
      - MIXED            => split == challenge
      - un family_id apare într-un singur split
    """

    model_config = ConfigDict(extra="forbid")

    claim_id: str
    claim: str
    label: Label
    topic: Topic

    claim_date: date
    """Data la care afirmația se evaluează. NU data publicării afirmației.

    Dacă afirmația spune „șomajul e 5%", fără an, `claim_date` fixează la ce an
    se referă. Fără câmpul ăsta, jumătate din afirmații devin neverificabile.
    """

    family_id: str
    """Grupează toate variantele aceleiași afirmații de bază.

    OBLIGATORIU. Controlează split-ul: toate variantele merg în același split,
    altfel ai leakage și rezultate umflate.
    """

    creation_method: CreationMethod
    perturbation_type: PerturbationType | None = None
    source_claim_url: str | None = None   # pentru real_claim: unde a fost rostită/publicată

    gold_evidence_ids: list[str] = Field(default_factory=list)
    requires_multi_evidence: bool = False

    annotator_id: str
    annotator_confidence: float = Field(ge=0.0, le=1.0)
    second_annotator_id: str | None = None
    adjudicated: bool = False
    annotation_notes: str | None = None

    split: Split | None = None

    # Marcaje pentru analizele din S10 — se completează la adnotare, nu la final
    has_number: bool = False
    has_date: bool = False
    has_negation: bool = False
    has_comparison: bool = False

    @model_validator(mode="after")
    def _label_evidence_coherent(self):
        if self.label == Label.NOT_ENOUGH_INFO and self.gold_evidence_ids:
            raise ValueError(
                f"{self.claim_id}: NOT_ENOUGH_INFO nu poate avea gold_evidence_ids. "
                "Dacă ai găsit dovadă, eticheta nu e NEI."
            )
        if self.label in (Label.SUPPORTED, Label.REFUTED) and not self.gold_evidence_ids:
            raise ValueError(
                f"{self.claim_id}: {self.label.value} cere cel puțin o dovadă gold."
            )
        if self.creation_method == CreationMethod.CONSTRUCTED and self.perturbation_type is None:
            raise ValueError(
                f"{self.claim_id}: afirmațiile 'constructed' cer perturbation_type "
                "(folosește NONE pentru varianta corectă)."
            )
        if self.label == Label.MIXED and self.split not in (None, Split.CHALLENGE):
            raise ValueError(f"{self.claim_id}: MIXED e permis doar în split-ul 'challenge'.")
        if self.requires_multi_evidence and len(self.gold_evidence_ids) < 2:
            raise ValueError(
                f"{self.claim_id}: requires_multi_evidence=True dar are "
                f"{len(self.gold_evidence_ids)} dovadă/dovezi."
            )
        return self


class ClaimPassagePair(BaseModel):
    """Adnotarea pe două axe a relației dintre o afirmație și un pasaj.

    Separarea celor două axe este contribuția metodologică a proiectului.
    `textual_relation` descrie ce spune pasajul; `evidence_quality` descrie cât
    valorează ca dovadă. Un articol poate SUPPORTS o afirmație falsă — atunci
    relația e SUPPORTS și calitatea e MISLEADING sau UNVERIFIED.
    """

    model_config = ConfigDict(extra="forbid")

    claim_id: str
    passage_id: str
    textual_relation: TextualRelation
    evidence_quality: EvidenceQuality | None = None  # None doar pentru IRRELEVANT
    negative_type: NegativeType | None = None
    annotator_id: str
    is_gold: bool = False
    """True dacă pasajul e suficient (singur sau împreună cu celelalte gold)
    pentru a stabili eticheta. Trebuie să apară și în Claim.gold_evidence_ids."""

    @model_validator(mode="after")
    def _quality_coherent(self):
        if self.textual_relation == TextualRelation.IRRELEVANT:
            if self.is_gold:
                raise ValueError(f"{self.claim_id}/{self.passage_id}: IRRELEVANT nu poate fi gold.")
        elif self.evidence_quality is None:
            raise ValueError(
                f"{self.claim_id}/{self.passage_id}: evidence_quality e obligatoriu "
                "pentru relații diferite de IRRELEVANT."
            )
        if self.is_gold and self.evidence_quality not in (
            EvidenceQuality.GOLD_PRIMARY,
            EvidenceQuality.CORROBORATIVE,
        ):
            raise ValueError(
                f"{self.claim_id}/{self.passage_id}: un pasaj gold trebuie să aibă "
                "evidence_quality GOLD_PRIMARY sau CORROBORATIVE."
            )
        return self


# --------------------------------------------------------------------------- #
# Snapshot                                                                     #
# --------------------------------------------------------------------------- #

class SnapshotEntry(BaseModel):
    """O intrare în manifestul unui snapshot. Manifestele SE COMIT în git."""

    model_config = ConfigDict(extra="forbid")

    source_id: str          # cheia din configs/sources.yaml
    resource: str           # ex. "une_rt_a" (Eurostat) sau "POP105A" (TEMPO)
    url: str
    retrieved_at: date
    raw_path: str           # relativ la rădăcina repo-ului
    content_hash: str
    n_records: int | None = None
    notes: str | None = None


class SnapshotManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot_id: str        # "YYYY-MM-DD"
    created_at: date
    schema_version: str = SCHEMA_VERSION
    entries: list[SnapshotEntry]


__all__ = [
    "SCHEMA_VERSION",
    "Claim",
    "ClaimPassagePair",
    "CreationMethod",
    "Document",
    "EvidenceQuality",
    "Label",
    "NegativeType",
    "Passage",
    "PerturbationType",
    "SnapshotEntry",
    "SnapshotManifest",
    "SourceTier",
    "Split",
    "TextualRelation",
    "Topic",
]
