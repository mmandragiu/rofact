"""Eurostat ingest (JSON-stat 2.0).

Endpoint, checked against the live API on 2026-09-21:

    https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{dataset}
        ?format=JSON&lang=EN&geo=RO&geo=EU27_2020&sinceTimePeriod=2010&...

Facts the code below depends on — each one was tested, not assumed:

- `lang` accepts only EN, FR and DE. `lang=RO` returns HTTP 400. So we download
  in English and translate the labels ourselves, keyed on the codes (LABELS_RO).
- An invalid code for a valid dimension (e.g. `sex=XX`) returns HTTP 200 with an
  empty `value: {}`. `fetch_dataset` turns that into an explicit error.
- Several values for one dimension are passed by repeating the parameter
  (`geo=RO&geo=BG`); `requests` does that when given a list.
- The response lists countries in its own order, not in the order requested.
  Decode through `dimension[d].category.index`, never through listing order.
- Dataset structures change over time: `ilc_li02` no longer has `indic_il`,
  it has `statinfo` + `rskpovth`.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Iterator, NamedTuple

from rofact import io
from rofact.ingest.base import load_sources_config, make_entry, polite_get, save_raw
from rofact.schemas import Document, SnapshotEntry, SourceTier

API_BASE = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"
DATA_BROWSER = "https://ec.europa.eu/eurostat/databrowser/view/{dataset}/default/table"


class Observation(NamedTuple):
    """One table cell, with every dimension resolved to its code and label."""

    dataset: str
    value: float
    dim_codes: dict[str, str]   # dimension -> code,  e.g. {"geo": "RO", "sex": "T"}
    dim_labels: dict[str, str]  # dimension -> label as delivered (EN), e.g. {"geo": "Romania"}
    time: str                   # "2023"
    status: str | None = None   # Eurostat flag: "p" provisional, "e" estimated, "b" break...


# --------------------------------------------------------------------------- #
# Download                                                                     #
# --------------------------------------------------------------------------- #

def fetch_dataset(dataset: str, snapshot_id: str, *,
                  params: dict[str, Any] | None = None,
                  lang: str = "EN") -> tuple[dict, SnapshotEntry]:
    """Download one dataset, save the raw response in the snapshot, return it."""
    query = {"format": "JSON", "lang": lang, **(params or {})}
    resp = polite_get(f"{API_BASE}/{dataset}", params=query)
    payload = resp.json()

    if not payload.get("value"):
        raise ValueError(
            f"Eurostat {dataset}: răspuns fără nicio observație pentru {query}. "
            "Aproape sigur un cod de dimensiune invalid — Eurostat întoarce HTTP 200 "
            "cu `value` gol în loc de eroare."
        )

    raw_path = save_raw(snapshot_id, "eurostat", dataset, resp.text)
    entry = make_entry("eurostat", dataset, resp.url, raw_path,
                       n_records=len(payload["value"]))
    return payload, entry


def extract_last_update(payload: dict) -> date | None:
    """Date of Eurostat's last data update; becomes Document.published_at."""
    for note in payload.get("extension", {}).get("annotation", []):
        if note.get("type") == "UPDATE_DATA" and note.get("date"):
            return date.fromisoformat(note["date"][:10])
    updated = payload.get("updated")
    return date.fromisoformat(updated[:10]) if updated else None


# --------------------------------------------------------------------------- #
# JSON-stat decoding                                                           #
# --------------------------------------------------------------------------- #

def iter_observations(payload: dict) -> Iterator[Observation]:
    """Turn JSON-stat's flat `value` vector into labelled observations.

    The keys of `value` are linear indices into an array of shape `size`, with the
    dimensions in the order of `id`. The last dimension varies fastest, so the
    position in each dimension is peeled off from the end with divmod:

        size = [2, 3]  ->  key 4  ->  divmod(4, 3) = (1, 1)  ->  positions [1, 1]
    """
    dataset = payload["extension"]["id"].lower()
    ids: list[str] = payload["id"]
    sizes: list[int] = payload["size"]
    dimensions = payload["dimension"]

    # position -> code, per dimension. `index` is either {code: position} or [code, ...].
    codes_by_position: list[list[str]] = []
    for dim in ids:
        index = dimensions[dim]["category"]["index"]
        if isinstance(index, list):
            codes_by_position.append(list(index))
        else:
            ordered = [""] * len(index)
            for code, position in index.items():
                ordered[position] = code
            codes_by_position.append(ordered)

    values = payload["value"]
    cells = values.items() if isinstance(values, dict) else enumerate(values)
    statuses = payload.get("status") or {}

    for key, value in cells:
        if value is None:
            continue
        rest = int(key)
        positions = []
        for size in reversed(sizes):
            rest, position = divmod(rest, size)
            positions.append(position)
        positions.reverse()

        codes = {dim: codes_by_position[i][positions[i]] for i, dim in enumerate(ids)}
        time = codes.pop("time")
        labels = {dim: dimensions[dim]["category"]["label"].get(code, code)
                  for dim, code in codes.items()}
        if isinstance(statuses, dict):
            status = statuses.get(str(key))
        else:
            status = statuses[int(key)] if int(key) < len(statuses) else None
        yield Observation(dataset, float(value), codes, labels, time, status)


# --------------------------------------------------------------------------- #
# Documents                                                                    #
# --------------------------------------------------------------------------- #

def _format_value(value: float) -> str:
    return str(int(value)) if value.is_integer() else repr(value)


def observations_to_documents(observations: list[Observation], dataset: str,
                              snapshot_id: str, *, dataset_label: str,
                              published_at: date | None,
                              license: str | None = None) -> list[Document]:
    """Pack a dataset's observations into ONE Document.

    The document is the unit of provenance (URL, licence, hash); passages built
    from it are the unit of retrieval. Its text is a TSV table of CODES and raw
    values — language-neutral and faithful to the source. Romanian labels are
    added later, when rows are read back (`rows_from_document`).

    Rows are sorted so the same data always yields the same text, hence the same
    content_hash: Eurostat does not return cells in a stable order.
    """
    if not observations:
        raise ValueError(f"Eurostat {dataset}: nicio observație, nu construiesc un document gol.")
    if license is None:
        license = load_sources_config()["sources"]["eurostat"]["license"]

    dims = list(observations[0].dim_codes)
    header = [*dims, "time", "value", "flag"]
    rows = sorted(
        [*(o.dim_codes[d] for d in dims), o.time, _format_value(o.value), o.status or ""]
        for o in observations
    )
    text = "\n".join("\t".join(row) for row in [header, *rows])

    return [Document(
        document_id=io.stable_id("estat", dataset, snapshot_id),
        source_url=DATA_BROWSER.format(dataset=dataset),
        title=dataset_label,
        source_type="official_statistics",
        source_tier=SourceTier.G1,
        domain="ec.europa.eu",
        published_at=published_at,
        retrieved_at=date.today(),
        snapshot_id=snapshot_id,
        content_hash=io.sha256_text(text),
        license=license,
        text=text,
    )]


def rows_from_document(doc: Document) -> list[dict[str, str]]:
    """Read a Eurostat document's table back as rows, adding Romanian labels.

    Each row keeps the codes ("geo": "RO") and gets, for every code that has a
    translation, a "<dimension>_ro" key ("geo_ro": "România").
    """
    header, *lines = doc.text.split("\n")
    columns = header.split("\t")
    rows = []
    for line in lines:
        row = dict(zip(columns, line.split("\t")))
        for dim, code in list(row.items()):
            label = LABELS_RO.get(dim, {}).get(code)
            if label:
                row[f"{dim}_ro"] = label
        rows.append(row)
    return rows


# --------------------------------------------------------------------------- #
# Facts: rows turned into Romanian-ready pieces                                #
# --------------------------------------------------------------------------- #

class Fact(NamedTuple):
    """One observation, with every piece already phrased in Romanian.

    This is the hand-over point between the two concerns: `eurostat.py` knows what
    the codes mean, `passages.py` knows how to build a Romanian sentence. Neither
    needs to learn the other's job.
    """

    indicator: str      # "rata șomajului"
    teritoriu: str      # "România"
    geo_code: str       # "RO"
    an: str             # "2023"
    defalcare: str      # "în rândul persoanelor de 15–74 de ani", or ""
    valoare: float      # 5.6
    um: str             # "%", "persoane", "milioane de euro", "la 1.000 de locuitori"
    precizare: str      # "din populația activă", or ""
    flag: str           # Eurostat flag, or ""
    group: tuple        # identical for every country of one comparison
    char_start: int     # where the source row sits in Document.text
    char_end: int


# How to phrase each dataset. `indicator_by` means the indicator's name depends on
# a dimension's code (GDP in euro vs GDP growth are different indicators, not the
# same one in different units).
VERBALIZATION: dict[str, dict[str, Any]] = {
    "une_rt_a": dict(
        indicator="rata șomajului",
        unit=("%", "din populația activă"),
        breakdown="age",
    ),
    "prc_hicp_aind": dict(
        indicator="rata anuală a inflației (IAPC)",
        unit=("%", ""),
    ),
    "nama_10_gdp": dict(
        indicator_by="unit",
        indicator_map={"CP_MEUR": "produsul intern brut",
                       "CLV_PCH_PRE": "creșterea reală a produsului intern brut"},
        unit_map={"CP_MEUR": ("milioane de euro", "prețuri curente"),
                  "CLV_PCH_PRE": ("%", "față de anul precedent")},
    ),
    "demo_gind": dict(
        indicator_by="indic_de",
        indicator_map={"JAN": "populația la 1 ianuarie",
                       "GBIRTHRT": "rata brută a natalității",
                       "GDEATHRT": "rata brută a mortalității",
                       "NATGROWRT": "rata sporului natural"},
        unit_map={"JAN": ("persoane", ""),
                  "GBIRTHRT": ("la 1.000 de locuitori", ""),
                  "GDEATHRT": ("la 1.000 de locuitori", ""),
                  "NATGROWRT": ("la 1.000 de locuitori", "")},
    ),
    "ilc_li02": dict(
        indicator="rata riscului de sărăcie",
        unit=("%", "prag de 60% din venitul median echivalent"),
    ),
}

BREAKDOWN_RO = {
    "age": {"Y15-74": "în rândul persoanelor de 15–74 de ani",
            "Y15-24": "în rândul tinerilor de 15–24 de ani",
            "TOTAL": ""},
    "sex": {"T": "", "M": "în rândul bărbaților", "F": "în rândul femeilor"},
}


def to_facts(doc: Document, dataset: str) -> list[Fact]:
    """Turn a Eurostat document's rows into Romanian-ready facts.

    Character offsets are tracked while walking the text, so every passage built
    later can point back to the exact line it came from.
    """
    spec = VERBALIZATION[dataset]
    lines = doc.text.split("\n")
    columns = lines[0].split("\t")
    offset = len(lines[0]) + 1          # skip the header line

    facts: list[Fact] = []
    for line in lines[1:]:
        start, offset = offset, offset + len(line) + 1
        row = dict(zip(columns, line.split("\t")))

        if "indicator_by" in spec:
            key = row[spec["indicator_by"]]
            indicator = spec["indicator_map"][key]
            um, precizare = spec["unit_map"][key]
        else:
            indicator = spec["indicator"]
            um, precizare = spec["unit"]

        dim = spec.get("breakdown")
        defalcare = BREAKDOWN_RO[dim][row[dim]] if dim else ""

        facts.append(Fact(
            indicator=indicator,
            teritoriu=LABELS_RO["geo"].get(row["geo"], row["geo"]),
            geo_code=row["geo"],
            an=row["time"],
            defalcare=defalcare,
            valoare=float(row["value"]),
            um=um,
            precizare=precizare,
            flag=row.get("flag", ""),
            group=(dataset, indicator, defalcare, row["time"]),
            char_start=start,
            char_end=start + len(line),
        ))
    return facts


def ingest(snapshot_id: str) -> tuple[list[Document], list[SnapshotEntry]]:
    """Download every dataset in STARTER_DATASETS; one Document per dataset."""
    documents: list[Document] = []
    entries: list[SnapshotEntry] = []
    for dataset, spec in STARTER_DATASETS.items():
        params = {"geo": GEO, "sinceTimePeriod": SINCE, **spec["params"]}
        payload, entry = fetch_dataset(dataset, snapshot_id, params=params)
        documents += observations_to_documents(
            list(iter_observations(payload)), dataset, snapshot_id,
            dataset_label=spec["label"], published_at=extract_last_update(payload),
        )
        entries.append(entry)
    return documents, entries


# --------------------------------------------------------------------------- #
# What we download (codes checked against the live API on 2026-09-21)          #
# --------------------------------------------------------------------------- #

EU27 = ["BE", "BG", "CZ", "DK", "DE", "EE", "IE", "EL", "ES", "FR", "HR", "IT", "CY",
        "LV", "LT", "LU", "HU", "MT", "NL", "AT", "PL", "PT", "RO", "SI", "SK", "FI", "SE"]
# All 27 member states, not just neighbours: claims like "the highest in the EU"
# can only be checked against every country.
GEO = [*EU27, "EU27_2020"]
SINCE = "2010"

STARTER_DATASETS: dict[str, dict[str, Any]] = {
    "une_rt_a": dict(
        label="Rata șomajului, date anuale", topic="economie",
        params={"sex": "T", "unit": "PC_ACT", "age": ["Y15-74", "Y15-24"]}),
    "prc_hicp_aind": dict(
        label="Rata anuală a inflației (IAPC)", topic="economie",
        params={"coicop": "CP00", "unit": "RCH_A_AVG"}),
    "nama_10_gdp": dict(
        label="Produsul intern brut", topic="economie",
        params={"na_item": "B1GQ", "unit": ["CP_MEUR", "CLV_PCH_PRE"]}),
    "demo_gind": dict(
        label="Indicatori demografici principali", topic="demografie",
        params={"indic_de": ["JAN", "GBIRTHRT", "GDEATHRT", "NATGROWRT"]}),
    "ilc_li02": dict(
        label="Rata riscului de sărăcie", topic="statistici_ro_ue",
        params={"statinfo": "MED_EI", "rskpovth": "B_60", "unit": "PC",
                "sex": "T", "age": "TOTAL"}),
}

# Romanian labels, keyed on codes. The API has no Romanian, and translating from
# the codes (not the English labels) keeps the wording under our control — INS's
# terms forbid distorting the meaning of the data.
LABELS_RO: dict[str, dict[str, str]] = {
    "geo": {
        "BE": "Belgia", "BG": "Bulgaria", "CZ": "Cehia", "DK": "Danemarca",
        "DE": "Germania", "EE": "Estonia", "IE": "Irlanda", "EL": "Grecia",
        "ES": "Spania", "FR": "Franța", "HR": "Croația", "IT": "Italia",
        "CY": "Cipru", "LV": "Letonia", "LT": "Lituania", "LU": "Luxemburg",
        "HU": "Ungaria", "MT": "Malta", "NL": "Țările de Jos", "AT": "Austria",
        "PL": "Polonia", "PT": "Portugalia", "RO": "România", "SI": "Slovenia",
        "SK": "Slovacia", "FI": "Finlanda", "SE": "Suedia",
        "EU27_2020": "Uniunea Europeană (27 de state membre)",
    },
    "sex": {"T": "total", "M": "bărbați", "F": "femei"},
    "age": {"Y15-74": "15–74 de ani", "Y15-24": "15–24 de ani", "TOTAL": "toate vârstele"},
    "unit": {
        "PC_ACT": "% din populația activă",
        "RCH_A_AVG": "rata medie anuală de variație (%)",
        "CP_MEUR": "milioane euro, prețuri curente",
        "CLV_PCH_PRE": "creștere reală, % față de anul precedent",
        "PC": "%",
    },
    "coicop": {"CP00": "indicele general al prețurilor de consum (IAPC)"},
    "na_item": {"B1GQ": "produsul intern brut (PIB)"},
    "indic_de": {
        "JAN": "populația la 1 ianuarie",
        "GBIRTHRT": "rata brută a natalității (la 1.000 de locuitori)",
        "GDEATHRT": "rata brută a mortalității (la 1.000 de locuitori)",
        "NATGROWRT": "rata sporului natural (la 1.000 de locuitori)",
    },
    "statinfo": {"MED_EI": "venitul median echivalent"},
    "rskpovth": {"B_60": "sub 60% din venitul median echivalent"},
    "freq": {"A": "anual"},
}
