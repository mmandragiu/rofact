# Registrul de surse — note operaționale

Configurația executabilă e în `configs/sources.yaml`. Documentul acesta conține
ce nu încape într-un YAML: cum se accesează efectiv fiecare sursă, ce capcane are,
și **starea verificării licenței**.

---

## Starea verificărilor

> **TODO S1 — 4h.** Nicio sursă nu se folosește în producție până nu are ambele
> coloane completate. Pune data la care ai verificat, nu doar bifa.

| Sursă | Tier | Licență verificată | `robots.txt` verificat | Data |
|---|---|---|---|---|
| Eurostat | G1 | ☐ | ☐ | |
| INS TEMPO | G1 | ☐ | ☐ | |
| data.gov.ro | G1 | ☐ (per dataset) | ☐ | |
| BNR | G2 | ☐ | ☐ | |
| Ministerul Finanțelor | G2 | ☐ | ☐ | |
| legislatie.just.ro | G2 | ☐ | ☐ | |
| Factual.ro | G3 | ☐ | ☐ | |
| AFP Fact Check RO | G3 | ☐ | ☐ | |
| media (×12–15) | MEDIA | ☐ | ☐ | |

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

**TODO:** la testarea inițială API-ul a răspuns gol prin proxy. Verifică local,
direct din browser sau cu `requests`, înainte să investești în `ingest/datagov.py`.
Dacă e indisponibil, alternativa pentru administrație publică sunt rapoartele de
activitate instituționale în PDF (tot G2).

**Licența diferă per dataset** — o iei din `license_id` / `license_title` și o pui
în `Document.license`. Nu presupune o licență globală.

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
