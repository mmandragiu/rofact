"""Legislation ingest, through the Ministry of Justice's official SOAP service.

    http://legislatie.just.ro/apiws/FreeWebService.svc/SOAP
    docs: https://legislatie.just.ro/ServiciulWebLegislatie.htm

Checked against the live service on 2026-10-23. Facts the code depends on — the
published documentation is incomplete, so each was verified:

- The endpoint needs the `/SOAP` suffix. Without it: HTTP 404.
- `Search` does NOT take flat parameters. It takes a `<SearchModel>` element
  (NumarPagina, RezultatePagina, SearchAn, SearchNumar, SearchText, SearchTitlu)
  followed by `tokenKey`.
- Flow: `GetToken` first, then `Search` with that token. Tokens expire.
- Response elements carry the `a:` namespace prefix (datacontract namespace).
- `Text` arrives clean: correct ș/ț, no replacement characters. `Emitent` does
  NOT — the server mangles it to "Pre?edintele României". Issuers are a small
  closed set, so ISSUERS repairs them by lookup rather than by guessing.
- Legal texts carry no line breaks: one continuous blob, with ASCII-art tables
  drawn in box characters. Segmentation must not rely on line starts.

Licence: official legislative texts are not copyright-protected (Law 8/1996).
Caveat recorded in the data card: consolidated versions on the portal are
unofficial; only the Monitorul Oficial print is legally authentic. `DataVigoare`
records which consolidated form was taken.
"""

from __future__ import annotations

import re
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date
from typing import Any, Iterator

from rofact import io
from rofact.ingest.base import USER_AGENT, make_entry, save_raw
from rofact.schemas import Document, SnapshotEntry, SourceTier

ENDPOINT = "http://legislatie.just.ro/apiws/FreeWebService.svc/SOAP"
ACTION = "http://tempuri.org/IFreeWebService/{op}"
TEMPURI = "http://tempuri.org/"
DATACONTRACT = "http://schemas.datacontract.org/2004/07/FreeWebService"
DOCUMENT_URL = "https://legislatie.just.ro/Public/DetaliiDocument/{id}"

DELAY = 2.0          # polite pause between calls; the service is not rate-documented
TIMEOUT = 120        # whole codes are ~1.5 MB of text


# --------------------------------------------------------------------------- #
# SOAP plumbing                                                                #
# --------------------------------------------------------------------------- #

RETRIES = 4
BACKOFF = 15         # the service returns 502/504 in bursts; it recovers on its own


def _call(op: str, body: str) -> str:
    """One SOAP call, retried on gateway errors.

    The service goes down in bursts (502/504 observed on 2026-10-23 while it had
    answered minutes earlier). Without retries an ingest of eight acts fails
    halfway and leaves the snapshot incomplete.
    """
    envelope = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">'
        f"<s:Body>{body}</s:Body></s:Envelope>"
    )
    request = urllib.request.Request(
        ENDPOINT, data=envelope.encode("utf-8"),
        headers={"Content-Type": "text/xml; charset=utf-8",
                 "SOAPAction": ACTION.format(op=op),
                 "User-Agent": USER_AGENT},
    )
    last: Exception | None = None
    for attempt in range(RETRIES):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                payload = response.read().decode("utf-8", "replace")
            time.sleep(DELAY)
            return payload
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code not in (429, 500, 502, 503, 504):
                raise
        except urllib.error.URLError as exc:
            last = exc
        if attempt < RETRIES - 1:
            time.sleep(BACKOFF * (attempt + 1))
    raise RuntimeError(
        f"legislatie: {op} a eșuat după {RETRIES} încercări ({last}). "
        "Serviciul Ministerului Justiției e intermitent — reia mai târziu."
    ) from last


def get_token() -> str:
    payload = _call("GetToken", f'<GetToken xmlns="{TEMPURI}"/>')
    match = re.search(r"<GetTokenResult[^>]*>(.*?)</GetTokenResult>", payload, re.DOTALL)
    if not match:
        raise RuntimeError(f"legislatie: GetToken nu a întors un token. Răspuns: {payload[:300]}")
    return match.group(1)


def search(token: str, *, an: str | None = None, numar: str | None = None,
           titlu: str | None = None, text: str | None = None,
           pagina: int = 1, rezultate: int = 10) -> list[dict[str, str]]:
    """One Search call. Returns the acts as plain dicts of strings."""
    criteria = "".join(
        f"<d:{name}>{value}</d:{name}>"
        for name, value in [("SearchAn", an), ("SearchNumar", numar),
                            ("SearchText", text), ("SearchTitlu", titlu)]
        if value
    )
    body = (
        f'<Search xmlns="{TEMPURI}">'
        f'<SearchModel xmlns:d="{DATACONTRACT}">'
        f"<d:NumarPagina>{pagina}</d:NumarPagina>"
        f"<d:RezultatePagina>{rezultate}</d:RezultatePagina>"
        f"{criteria}</SearchModel>"
        f"<tokenKey>{token}</tokenKey></Search>"
    )
    root = ET.fromstring(_call("Search", body))
    acts = []
    for node in root.iter(f"{{{DATACONTRACT}}}Legi"):
        acts.append({child.tag.split("}")[-1]: (child.text or "") for child in node})
    return acts


# --------------------------------------------------------------------------- #
# Cleaning                                                                     #
# --------------------------------------------------------------------------- #

# The service mangles ș/ț in metadata fields ("Pre?edintele României") though the
# act text itself is clean. Issuers are a small closed set, so they are repaired by
# lookup — never by guessing which letter a "?" used to be.
ISSUERS = {
    "Pre?edintele României": "Președintele României",
    "Curtea Constitu?ională": "Curtea Constituțională",
    "Înalta Curte de Casa?ie ?i Justi?ie": "Înalta Curte de Casație și Justiție",
    "Ministerul Finan?elor Publice": "Ministerul Finanțelor Publice",
    "Ministerul Finan?elor": "Ministerul Finanțelor",
    "Ministerul Educa?iei": "Ministerul Educației",
    "Ministerul Să?ătă?ii": "Ministerul Sănătății",
    "Ministerul Justi?iei": "Ministerul Justiției",
    "Agen?ia Na?ională de Administrare Fiscală": "Agenția Națională de Administrare Fiscală",
}

# Box-drawing runs are ASCII-art tables inside the legal text. Kept as a single
# marker rather than deleted: a passage that silently drops a table would look
# complete while missing exactly the numbers a claim may rest on.
_BOX_RUN = re.compile(r"[─│┌┐└┘├┤┬┴┼━┃]{2,}")
_SPACES = re.compile(r"[ \t ]+")


def clean_text(text: str) -> str:
    """Normalise an act's text without changing what it says."""
    text = _BOX_RUN.sub(" […tabel…] ", text)
    text = _SPACES.sub(" ", text.replace("\n", " "))
    return io.normalize_text(text)


def repair_issuer(emitent: str) -> str:
    if emitent in ISSUERS:
        return ISSUERS[emitent]
    if "?" in emitent:
        # Unknown issuer with lost characters: keep it, but say so rather than
        # inventing letters. The data card lists this as a known limitation.
        return emitent
    return emitent


def parse_vigoare(value: str) -> date | None:
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# Documents                                                                    #
# --------------------------------------------------------------------------- #

def act_to_document(act: dict[str, str], snapshot_id: str,
                    license: str) -> Document | None:
    """Build a G2 Document from one act. Returns None when the act has no text."""
    text = clean_text(act.get("Text", ""))
    if len(text) < 200:
        return None

    numar = act.get("Numar", "")
    tip = act.get("TipAct", "ACT")
    vigoare = parse_vigoare(act.get("DataVigoare", ""))
    link = act.get("LinkHtml", "")
    doc_id_source = link.rstrip("/").rsplit("/", 1)[-1] or f"{tip}-{numar}"

    titlu = io.normalize_text(act.get("Titlu", "")) or f"{tip} nr. {numar}"

    return Document(
        document_id=io.stable_id("lege", doc_id_source, snapshot_id),
        source_url=link.replace("http://", "https://") or DOCUMENT_URL.format(id=doc_id_source),
        title=titlu[:300],
        source_type="law",
        source_tier=SourceTier.G2,
        domain="legislatie.just.ro",
        published_at=vigoare,
        retrieved_at=date.today(),
        snapshot_id=snapshot_id,
        content_hash=io.sha256_text(text),
        license=license,
        text=text,
    )


def ingest(snapshot_id: str) -> tuple[list[Document], list[SnapshotEntry]]:
    """Fetch every act in ACTS. One Document per act."""
    from rofact.ingest.base import load_sources_config

    license = load_sources_config()["sources"]["legislatie_just"]["license"]
    token = get_token()

    documents: list[Document] = []
    entries: list[SnapshotEntry] = []
    for spec in ACTS:
        results = search(token, an=spec["an"], numar=spec["numar"], rezultate=10)
        act = pick_act(results, spec)
        if act is None:
            print(f"    ! {spec['numar']}/{spec['an']} ({spec['eticheta']}): negăsit")
            continue

        resource = f"{spec['numar']}-{spec['an']}"
        raw_path = save_raw(snapshot_id, "legislatie", resource,
                            act.get("Text", ""), ext="txt")
        document = act_to_document(act, snapshot_id, license)
        if document is None:
            print(f"    ! {resource}: text prea scurt, sărit")
            continue
        documents.append(document)
        entries.append(make_entry("legislatie_just", resource,
                                  document.source_url, raw_path,
                                  n_records=1,
                                  notes=f"DataVigoare={act.get('DataVigoare', '?')}"))
    return documents, entries


def pick_act(results: list[dict[str, str]], spec: dict[str, Any]) -> dict[str, str] | None:
    """Choose the act itself, not its amendments or implementing norms.

    A search for 227/2015 returns the law, the consolidated code, the decree that
    promulgated it and the methodological norms. The wanted one is the longest
    whose title contains the expected keyword — amendments are short, norms carry
    a different title.
    """
    keyword = spec.get("contine", "").lower()
    candidates = [a for a in results
                  if keyword in io.normalize_text(a.get("Titlu", "")).lower()]
    if not candidates:
        candidates = results
    return max(candidates, key=lambda a: len(a.get("Text", "")), default=None)


# --------------------------------------------------------------------------- #
# Which acts we fetch                                                          #
# --------------------------------------------------------------------------- #
#
# Deliberately a short, targeted list — the plan is explicit that the legislative
# corpus is NOT to be indexed wholesale (20-30 acts, ~1,500 passages). Claims are
# restricted to literally verifiable facts: whether an article exists, a date of
# entry into force, a numeric threshold, a repeal. Not interpretation.
#
# Extend this list as claims demand; keep `contine` specific enough that
# `pick_act` does not pick up the implementing norms instead of the act.

ACTS: list[dict[str, Any]] = [
    dict(an="2015", numar="227", contine="codul fiscal",
         eticheta="Codul fiscal", topic="legislatie"),
    dict(an="2003", numar="53", contine="codul muncii",
         eticheta="Codul muncii", topic="legislatie"),
    dict(an="2001", numar="544", contine="informatiilor de interes public",
         eticheta="Liberul acces la informațiile de interes public", topic="administratie_publica"),
    dict(an="2016", numar="98", contine="achizitiile publice",
         eticheta="Achizițiile publice", topic="administratie_publica"),
    dict(an="2010", numar="263", contine="sistemul unitar de pensii",
         eticheta="Sistemul unitar de pensii publice", topic="administratie_publica"),
    dict(an="2006", numar="273", contine="finantele publice locale",
         eticheta="Finanțele publice locale", topic="administratie_publica"),
    dict(an="2022", numar="179", contine="date deschise",
         eticheta="Datele deschise și reutilizarea informațiilor", topic="administratie_publica"),
    dict(an="2007", numar="109", contine="reutilizarea informatiilor",
         eticheta="Reutilizarea informațiilor din instituțiile publice", topic="administratie_publica"),
]
