# Registrul de surse — note operaționale

Configurația executabilă e în `configs/sources.yaml`. Documentul acesta conține
ce nu încape într-un YAML: cum se accesează efectiv fiecare sursă, ce capcane are,
și **starea verificării licenței**.

---

## Starea verificărilor

> **Verificat complet: 2026-08-05.** Fiecare rând are data la care au fost citiți
> termenii, nu doar bifa. Configurația executabilă corespunzătoare e în
> `configs/sources.yaml` (câmpurile `license_status`, `access`, `robots_checked`).

| Sursă | Tier | Licență | `robots.txt` | Acces | Verdict | Data |
|---|---|---|---|---|---|---|
| Eurostat | G1 | ✅ | n/a (API public) | api | reutilizare liberă cu atribuire | 2026-08-05 |
| INS TEMPO | G1 | ✅ **email** | n/a | **manual_download** | liber cu atribuire, **doar descărcare manuală** | 2026-08-04 |
| data.gov.ro | G1 | ✅ per dataset | n/a | api (CKAN) | CC-BY-4.0 / OGL-ROU-1.0 | 2026-08-05 |
| BNR | G2 | ✅ | ✅ permisiv | download | redistribuire cu indicarea sursei | 2026-08-05 |
| Ministerul Finanțelor | G2 | ⚠️ inferență | ✅ permisiv | download | ok — fără termeni expliciți | 2026-08-05 |
| legislatie.just.ro | G2 | ✅ | ⚠️ inaccesibil | **api (SOAP)** | texte în domeniu public (L. 8/1996) | 2026-08-05 |
| Factual.ro | G3 | ✅ restrictiv | ⛔ `Disallow: /` | manual_discovery | doar descoperire, fără text | 2026-08-05 |
| AFP Fact Check RO | G3 | ⚠️ conservator | ⚠️ SSL expirat | manual_discovery | doar descoperire, fără text | 2026-08-05 |
| media (×12–15) | MEDIA | ☐ | ☐ | — | **TODO S4** | — |

### Ce a rezultat, pe scurt

**Nicio sursă respinsă.** Trei și-au schimbat modul de acces față de planul inițial:

| Sursă | Din | În | De ce |
|---|---|---|---|
| INS TEMPO | client API | descărcare manuală | răspuns scris de la INS: „datele din TEMPO se descarcă doar manual" |
| legislatie.just.ro | scraping (8h) | **API SOAP oficial** (~3h) | ministerul publică un serviciu web documentat |
| Factual.ro / AFP | scraping | descoperire manuală | `robots.txt` interzice explicit (Factual); drepturi rezervate (AFP) |

**Două clauze cu impact metodologic**, ambele întărind discipline pe care le aveam
deja din motive științifice:

- **INS — nedenaturare:** „orice denaturare de la semnificația reală a datelor este
  interzisă". Se aplică direct verbalizării tabelelor: „populația rezidentă" nu
  devine „populația României".
- **BNR — semnalarea alterării:** „în cazul alterării informației preluate, acest
  lucru trebuie menționat explicit". În data card declarăm că pasajele G2 sunt
  fragmente extrase, netransformate; `char_start`/`char_end` asigură trasabilitatea.

**De declarat în data card ca limitări:**
1. ground truth-ul pentru legislație se bazează pe **forme consolidate neoficiale**
   (doar Monitorul Oficial e autentic juridic);
2. licența Ministerului Finanțelor e stabilită prin **inferență din cadrul legal**
   (L. 544/2001 + L. 8/1996 art. 9 + L. 179/2022), nu prin termeni expliciți;
3. acoperirea INS e limitată de cerința de descărcare manuală — un număr restrâns
   de matrici selectate, nu întreaga bază TEMPO.

**Opțional, nefăcut:** email de confirmare către `publicinfo@mfinante.gov.ro`, care
ar transforma inferența juridică de la punctul 2 într-o confirmare scrisă (același
procedeu care a funcționat la INS).

---

## Eurostat

**Acces:** REST, fără cheie.

```
https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{dataset}
    ?format=JSON&lang=RO&geo=RO&sex=T&unit=PC_ACT
```

Răspunsul e **JSON-stat 2.0**: un vector plat `value` plus `dimension` cu indexul
fiecărei dimensiuni. Cheile din `value` sunt indici liniari — trebuie decodate
folosind `size` și ordinea din `id`. Vezi `ingest/eurostat.py`.

**Capcane:**

- Coduri de dimensiune invalide **nu dau eroare** — întorc `value: {}` gol și
  categoria goală în `dimension`. Verifică întotdeauna că ai primit date; altfel
  vei crede că indicatorul nu există.
- `lang=RO` traduce etichetele, ceea ce e util pentru verbalizare în română.
- `extension.annotation` conține `UPDATE_DATA` — folosește-l ca `published_at`.
- Baza **nu versionează** valorile istorice. De aici toată disciplina de snapshot.

---

## INS TEMPO Online

**Acces:** API JSON nedocumentat public, pe portul 8077, HTTP (nu HTTPS).

```
GET http://statistici.insse.ro:8077/tempo-ins/context/{code}     # arborele tematic
GET http://statistici.insse.ro:8077/tempo-ins/matrix/{matrix}    # metadate + dimensiuni
POST http://statistici.insse.ro:8077/tempo-ins/matrix/dataSet/{matrix}   # datele
```

**Arborele tematic.** `context/1` → „A. STATISTICA SOCIALA", cu copii `10`
(populație), `11` (mișcarea naturală), `12` (migrație), `15` (forța de muncă),
`20` (venituri), etc. Navighezi recursiv până la matrici.

**Metadatele unei matrici** (`/matrix/POP105A`) întorc:

- `matrixName` — denumirea completă;
- `dimensionsMap` — lista dimensiunilor, fiecare cu opțiuni având `nomItemId` și
  `offset`. Acestea sunt ID-urile pe care le trimiți ca să ceri date;
- `definitie`, `metodologie`, `observatii` — **text narativ oficial**;
- `ultimaActualizare` — folosește-l ca `published_at`;
- `periodicitati`, `surseDeDate`.

> **Aurul ascuns:** `definitie` și `metodologie` sunt pasaje G1 gata făcute. Multe
> afirmații false se sprijină pe confuzii de definiție — „populația rezidentă" vs.
> „populația după domiciliu" e exemplul canonic, cu diferență de milioane de
> persoane. Fără pasajele de definiție, claims-urile de tip `scope_shift` sunt
> imposibil de dovedit.

**Cererea de date.** Endpoint-ul `dataSet` e POST cu un corp JSON care conține
selecția de `nomItemId` per dimensiune. **Formatul exact nu e documentat și se
schimbă ocazional** — deschide TEMPO în browser, DevTools → Network, selectează
manual o defalcare mică și copiază payload-ul real. Notează-l în docstring-ul
funcției din `ingest/ins_tempo.py`, cu data.

**Capcane:**

- HTTP simplu, port nestandard — poate fi blocat de firewall corporate/școală.
- Fără rate limit documentat: pune delay 1–2s și nu paraleliza.
- Cere defalcări **mici**. `POP105A` are 104 grupe de vârstă × 3 sexe × 3 medii ×
  55 de unități teritoriale × 23 de ani. Cererea completă e inutilă și abuzivă —
  selectează exact ce îți trebuie (ex. Total/Total/Total/TOTAL × toți anii).
- Datele sunt revizuite constant. `observatii` spune ce ani sunt „revizuiți".

---

## data.gov.ro

**Acces:** CKAN API standard.

```
https://data.gov.ro/api/3/action/package_search?q={query}&rows={n}
https://data.gov.ro/api/3/action/package_show?id={dataset_id}
```

**Stare API: verificat funcțional (2026-07-28).** TODO-ul anterior („a răspuns
gol prin proxy") era un artefact de rețea, nu o problemă a portalului.

    status_show      -> HTTP 200
    package_list     -> 5.214 seturi de date
    package_search?q=buget&rows=3  -> 185 rezultate

Fără cheie de API pentru citire (cheia e necesară doar la *crearea* de seturi).
Documentația: https://data.gov.ro/pages/developers

**Licența diferă per dataset** — o iei din `license_id` / `license_title` și o pui
în `Document.license`. Nu presupune o licență globală. Verificat pe un eșantion de
50 de seturi: **toate** au licență declarată, doar două valori —
`CC-BY-4.0` (~56%) și `uk-ogl` / `OGL-ROU-1.0` (~44%), ambele permisive cu
atribuire. Regulă operațională: un set fără licență declarată nu se include.

### Capcana reală: formatele

API-ul întoarce **doar metadate**. Datele propriu-zise sunt fișiere atașate, iar
distribuția lor (pe 133 de resurse verificate) e:

| Format | Pondere |
|---|---|
| XLSX / XLS | ~80% |
| PDF | ~20% |
| CSV | 1 resursă din 133 |

Fiecare instituție își structurează Excel-ul altfel — antete pe rânduri diferite,
foi multiple, denumiri de coloane proprii. **Nu există parser generic**; fiecare
set cere mapare manuală. Multe seturi au `metadata_modified` în 2023 sau mai
devreme, deci actualizarea nu e garantată.

**Decizie de luat la S3** (nu acum), pentru cele 110 claims de administrație:

| Opțiune | Ce implică |
|---|---|
| A. data.gov.ro restrâns | 5–8 seturi cu structură consistentă, mapate manual o dată. Un tabel bugetar dă multe valori, deci 110 claims e fezabil |
| B. Pivot pe rapoarte PDF instituționale | Text narativ cu `pdfplumber` (deja în requirements). Pasaje mai naturale pentru retrieval decât tabelele verbalizate |
| C. Mixt | 2–3 seturi Excel pentru cifre + PDF-uri pentru context narativ. Probabil cel mai bun raport valoare/efort |

Dacă alegi Excel: adaugă `openpyxl` (pentru `.xlsx`) și `xlrd` (pentru `.xls`) în
`requirements.txt` — pandas nu le citește fără ele.

---

## legislatie.just.ro

**Acces:** fără API. Scraping, cu disciplină.

- **Verifică `robots.txt` înainte de orice request.** Dacă interzice, oprește-te
  și folosește Monitorul Oficial sau descarcă manual actele.
- delay ≥ 3s, User-Agent identificabil cu contact;
- **maximum 20–30 de acte normative.** Nu indexezi corpusul legislativ; alegi
  actele relevante pentru afirmațiile pe care le ai.

**Segmentare pe articol**, nu pe fereastră de cuvinte. Articolul e unitatea
naturală de citare, iar `Passage.section` primește „Art. 12", „Art. 12 alin. (3)".
Un fact-checker care citează „un fragment de 150 de cuvinte din legea X" nu e util;
unul care citează „Art. 12 alin. (3)" e.

**Capcană majoră:** formele consolidate vs. formele istorice. O lege modificată de
cinci ori are cinci forme. Snapshotul trebuie să rețină **care formă** ai luat și
la ce dată era în vigoare — altfel afirmațiile despre praguri numerice devin
neverificabile.

---

## Factual.ro și AFP Fact Check România (G3)

**Folosire strict pentru descoperire.** Extragi:

1. afirmația publică (cine, când, unde a spus-o);
2. lista surselor primare pe care articolul le citează.

Apoi te întorci la sursa primară și **produci propria etichetă**.

Verdictul lor nu se copiază niciodată. Motivul nu e doar metodologic — un dataset
care copiază verdicte e o replicare a muncii altcuiva, nu o contribuție.

**Stocare:** preferabil doar URL + afirmația extrasă, nu articolul integral.
Verifică termenii înainte. AFP în special are drepturi rezervate stricte.

---

## Sursele media

**TODO S4.** Criterii de selecție pentru cele 12–15 publicații:

| Criteriu | De ce |
|---|---|
| diversitate de **tip** (agenție / cotidian / economic / regional / online-only) | tipuri diferite au comportamente diferite față de sursa primară |
| diversitate **editorială** (nu toate din aceeași familie de proprietate) | altfel duplicatele nu sunt un fenomen, ci un artefact al selecției |
| arhivă accesibilă pe perioada de interes | fără asta nu poți acoperi anii din claims |
| `robots.txt` permisiv pentru crawl-ul tău | condiție eliminatorie |

**Nu selecta publicații după „credibilitate"** și nu construi o ierarhie de
încredere pe outlet. Proiectul studiază *tipuri de comportament față de dovadă*
(repetă, parafrazează, omite context, folosește date vechi), nu reputația
brandurilor. Un feature „outlet X = adevăr" ar fi exact eroarea pe care spec-ul o
interzice la §9E.

---

## Note de conformitate

- Nimic din corpus nu se republică integral fără verificarea licenței.
- Pasajele scurte folosite ca dovadă intră de regulă la citare, dar asta se
  documentează în data card, nu se presupune.
- Fiecare crawler trimite un User-Agent identificabil, cu adresă de contact.
- Dacă o sursă cere oprirea, se oprește — și se notează în `journal.md`.
