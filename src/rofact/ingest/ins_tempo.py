"""INS TEMPO Online ingest — parser for MANUAL exports.

Not an API client, by instruction. INS answered a written request on 2026-08-04:

    (1) reuse needs no prior agreement, only attribution;
    (2) redistributing the data together with the definitions and methodological
        notes is allowed, with the source named;
    (3) data in TEMPO Online may be downloaded ONLY MANUALLY.

So the undocumented API on port 8077 is not used. The flow is:

    you            -> select a matrix in https://statistici.insse.ro/tempoins/,
                      keep the breakdown small, export CSV
                   -> save it under data/raw/ins_tempo/
    this module    -> parse, hash, build Documents

Export format, checked on a real POP105A file (2026-10-23):

    Varste si grupe de varsta, Sexe, Medii de rezidenta, Macroregiuni  regiuni
    de dezvoltare si judete, Ani, UM: Numar persoane, Valoare
    Total, Total, Total, TOTAL, Anul 2024, Numar persoane, 19068290

- separator is ", " (comma AND space); commas inside a dimension name are
  replaced by a space in the header, which is why "Macroregiuni  regiuni" has a
  double space;
- years arrive as "Anul 2024";
- the unit is in the column NAME ("UM: Numar persoane"), not only in the cells;
- the text carries NO DIACRITICS ("Varste si grupe de varsta"), exactly like the
  API did. Romanian labels are ours to add — see LABELS_RO.

Attribution required (configs/sources.yaml):
    Sursa: INS România, {matrix_name}, {year}, www.insse.ro
"""

from __future__ import annotations

import csv
import re
from datetime import date
from pathlib import Path
from typing import Any

from rofact import io
from rofact.ingest.base import make_entry
from rofact.passages import Fact
from rofact.schemas import Document, SnapshotEntry, SourceTier

EXPORT_DIR = io.RAW / "ins_tempo"
TEMPO_URL = "https://statistici.insse.ro/tempoins/index.jsp?page=tables&matrix={matrix}"

YEAR = re.compile(r"Anul\s+(\d{4})")
TOTALS = {"total", "totale"}


# --------------------------------------------------------------------------- #
# Parsing                                                                      #
# --------------------------------------------------------------------------- #

def matrix_from_filename(path: Path) -> str:
    """'exportPivot_POP105A.csv' -> 'POP105A'."""
    stem = path.stem
    match = re.search(r"([A-Z]{3}\d+[A-Z]?)", stem.upper())
    return match.group(1) if match else stem.upper()


def read_export(path: Path) -> tuple[list[str], list[list[str]]]:
    """Read one manual export. Returns (header, rows), both whitespace-trimmed."""
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = [[cell.strip() for cell in row]
                for row in csv.reader(f) if any(cell.strip() for cell in row)]
    if not rows:
        raise ValueError(f"{path.name}: fișier gol")
    header, *data = rows
    if header[-1].lower() != "valoare":
        raise ValueError(
            f"{path.name}: ultima coloană ar trebui să fie 'Valoare', dar e "
            f"{header[-1]!r}. Ai exportat formatul Pivot din TEMPO?"
        )
    return header, data


def _parse_value(cell: str) -> float | None:
    """INS writes plain integers; ':' and '-' mark a missing observation."""
    cell = cell.replace(" ", "").replace(".", "")
    if cell in {"", ":", "-", "*"}:
        return None
    try:
        return float(cell.replace(",", "."))
    except ValueError:
        return None


def parse_export(path: Path) -> list[dict[str, str]]:
    """Turn an export into rows keyed by column name, with the year isolated."""
    header, data = read_export(path)
    parsed = []
    for row in data:
        record = dict(zip(header, row))
        for column, value in list(record.items()):
            year = YEAR.fullmatch(value)
            if year:
                record["__an__"] = year.group(1)
                record["__col_an__"] = column
        parsed.append(record)
    return parsed


# --------------------------------------------------------------------------- #
# Documents                                                                    #
# --------------------------------------------------------------------------- #

def export_to_document(path: Path, snapshot_id: str, license: str) -> Document:
    """One Document per exported matrix.

    Like Eurostat, the document's text is the table itself — codes and raw values,
    kept faithful to the source. Romanian labels are added later, when rows are
    read back into Facts, so fixing a label never changes the content hash.
    """
    matrix = matrix_from_filename(path)
    spec = MATRICES.get(matrix, {})
    header, data = read_export(path)
    text = "\n".join("\t".join(row) for row in [header, *sorted(data)])

    return Document(
        document_id=io.stable_id("ins", matrix, snapshot_id),
        source_url=TEMPO_URL.format(matrix=matrix),
        title=spec.get("label", f"INS TEMPO {matrix}"),
        source_type="official_statistics",
        source_tier=SourceTier.G1,
        domain="insse.ro",
        published_at=None,          # TEMPO exports carry no release date
        retrieved_at=date.fromtimestamp(path.stat().st_mtime),
        snapshot_id=snapshot_id,
        content_hash=io.sha256_text(text),
        license=license,
        text=text,
    )


def to_facts(doc: Document, matrix: str) -> list[Fact]:
    """Turn an INS table into Romanian-ready facts.

    Dimension handling is generic rather than per-matrix: every column other than
    the year, the unit and the value is a breakdown, and breakdowns whose value is
    "Total" are dropped — nobody says "the resident population, total ages, total
    sexes", they just say "the resident population".
    """
    spec = MATRICES.get(matrix, {})
    lines = doc.text.split("\n")
    header = lines[0].split("\t")
    offset = len(lines[0]) + 1

    unit_column = next((c for c in header if c.lower().startswith("um")), None)
    year_column = next((c for c in header if c.strip().lower() == "ani"), None)
    territory_column = next((c for c in header if "judete" in c.lower()
                             or "macroregiuni" in c.lower()), None)

    facts: list[Fact] = []
    for line in lines[1:]:
        start, offset = offset, offset + len(line) + 1
        row = dict(zip(header, line.split("\t")))

        value = _parse_value(row.get("Valoare", ""))
        if value is None:
            continue
        year_match = YEAR.search(row.get(year_column, "")) if year_column else None
        if not year_match:
            continue
        an = year_match.group(1)

        teritoriu_raw = row.get(territory_column, "TOTAL") if territory_column else "TOTAL"
        teritoriu = ("România" if teritoriu_raw.strip().lower() in TOTALS
                     else label_ro(teritoriu_raw))

        breakdown = [
            label_ro(row[column])
            for column in header
            if column not in (unit_column, year_column, territory_column, "Valoare")
            and row.get(column, "").strip().lower() not in TOTALS
            and row.get(column, "").strip()
        ]
        defalcare = ", ".join(b for b in breakdown if b)

        indicator = spec.get("indicator", f"indicatorul {matrix}")
        facts.append(Fact(
            indicator=indicator,
            teritoriu=teritoriu,
            geo_code="RO" if teritoriu == "România" else teritoriu_raw,
            an=an,
            defalcare=defalcare,
            valoare=value,
            um=spec.get("um") or _unit_from_column(unit_column),
            precizare=spec.get("precizare", ""),
            flag="",
            group=(matrix, indicator, defalcare, an),
            char_start=start,
            char_end=start + len(line),
        ))
    return facts


def _unit_from_column(column: str | None) -> str:
    """'UM: Numar persoane' -> 'persoane'."""
    if not column:
        return ""
    unit = column.split(":", 1)[-1].strip().lower()
    return {"numar persoane": "persoane", "procente": "%", "numar": ""}.get(unit, unit)


def ingest(snapshot_id: str) -> tuple[list[Document], list[SnapshotEntry]]:
    """Parse every manual export found in data/raw/ins_tempo/."""
    from rofact.ingest.base import load_sources_config

    license = load_sources_config()["sources"]["ins_tempo"]["license"]
    exports = sorted(EXPORT_DIR.glob("*.csv"))
    if not exports:
        raise NotImplementedError(
            f"ins_tempo: niciun export în {EXPORT_DIR}. Datele TEMPO se descarcă "
            "MANUAL (confirmat de INS, 2026-08-04): exportă CSV din "
            "https://statistici.insse.ro/tempoins/ și pune fișierele acolo."
        )

    documents, entries = [], []
    for path in exports:
        matrix = matrix_from_filename(path)
        document = export_to_document(path, snapshot_id, license)
        documents.append(document)
        entries.append(make_entry("ins_tempo", matrix, document.source_url, path,
                                  n_records=len(parse_export(path)),
                                  notes="export manual din interfața TEMPO"))

    for path in sorted(EXPORT_DIR.glob("*_metodologie.txt")):
        matrix = matrix_from_filename(path)
        document = methodology_to_document(path, snapshot_id, license)
        documents.append(document)
        entries.append(make_entry("ins_tempo", f"{matrix}-metodologie",
                                  document.source_url, path, n_records=1,
                                  notes="definiție + metodologie, copiate manual din TEMPO"))
    return documents, entries


def methodology_to_document(path: Path, snapshot_id: str, license: str) -> Document:
    """A matrix's definition and methodology, as a narrative G1 document.

    These are worth more than they look. Many false claims rest on a confusion of
    definitions: "resident population" (POP105A) and "population by domicile"
    (POP107D) differ by 2.8 million people in 2024. Without the passage defining
    each one, a `scope_shift` claim cannot be settled — there would be two official
    numbers and nothing saying why both are right.

    INS confirmed in writing (2026-08-04) that the definitions and methodological
    notes may be redistributed together with the data, with the source named.

    The text is copied by hand from the matrix page in TEMPO (manual download only),
    saved as `<MATRIX>_metodologie.txt`. It is kept exactly as copied — the source
    of a G1 passage is never edited — and segmented as narrative text.
    """
    matrix = matrix_from_filename(path)
    spec = MATRICES.get(matrix, {})
    text = io.normalize_text(path.read_text(encoding="utf-8-sig"))
    if len(text) < 50:
        raise ValueError(f"{path.name}: prea scurt — ai copiat definiția întreagă?")

    return Document(
        document_id=io.stable_id("ins_meta", matrix, snapshot_id),
        source_url=TEMPO_URL.format(matrix=matrix),
        title=f"Definiție și metodologie — {spec.get('label', matrix)}",
        source_type="official_methodology",
        source_tier=SourceTier.G1,
        domain="insse.ro",
        published_at=None,
        retrieved_at=date.fromtimestamp(path.stat().st_mtime),
        snapshot_id=snapshot_id,
        content_hash=io.sha256_text(text),
        license=license,
        text=text,
    )


# --------------------------------------------------------------------------- #
# What the matrices mean                                                       #
# --------------------------------------------------------------------------- #
#
# Extend as you export more matrices. A matrix with no entry still works — it
# falls back to "indicatorul <COD>" — but the passages read badly, so add it.

MATRICES: dict[str, dict[str, Any]] = {
    "POP105A": dict(
        label="Populația rezidentă la 1 ianuarie, pe grupe de vârstă, sexe și medii",
        indicator="populația rezidentă la 1 ianuarie",
        um="persoane", topic="demografie",
    ),
    "POP107D": dict(
        label="Populația după domiciliu la 1 ianuarie",
        indicator="populația după domiciliu la 1 ianuarie",
        um="persoane", topic="demografie",
        # The pair POP105A/POP107D differs by millions of people. It is the canonical
        # source of `scope_shift` claims: a statement that confuses the two is
        # REFUTED, and the proof is the definition, not only the number.
    ),
}

# TEMPO delivers everything without diacritics. Labels are ours, keyed on the exact
# string the export contains.
LABELS_RO: dict[str, str] = {
    "Masculin": "bărbați",
    "Feminin": "femei",
    "Urban": "mediul urban",
    "Rural": "mediul rural",
    "Numar persoane": "persoane",
}


def label_ro(value: str) -> str:
    """Romanian label for a raw INS cell; falls back to the value as delivered."""
    value = value.strip()
    return LABELS_RO.get(value, value)
