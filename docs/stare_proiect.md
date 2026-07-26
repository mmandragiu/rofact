# RoFact — starea proiectului (fișier de continuitate între sesiuni)

> **Cum se folosește:** la începutul fiecărei sesiuni noi de lucru cu un asistent AI,
> atașează fișierul acesta. Conține tot ce trebuie ca să se reia lucrul fără să
> reexplici proiectul. Se actualizează la finalul fiecărei sesiuni — secțiunile
> §6 (jurnal) și §7 (unde suntem) sunt cele care se modifică.

**Ultima actualizare:** 2026-07-24 · **Sesiunea:** S3 (prima cu Claude Code)

---

## 1. Ce este RoFact, în trei propoziții

Un sistem de verificare automată a afirmațiilor în limba română. Primește o afirmație
factuală, caută dovezi într-un corpus care amestecă surse oficiale cu presă, și
întoarce `SUPPORTED` / `REFUTED` / `NOT_ENOUGH_INFO` împreună cu pasajele-dovadă,
sursele, o explicație și un scor de încredere calibrat.

**Întrebarea de cercetare** (contribuția, nu doar inginerie):

> Cât de mult scade performanța unui fact-checker românesc când sursele oficiale
> sunt amestecate cu articole media incomplete, repetitive, vechi sau contradictorii?

**Ce înseamnă un verdict:** „aceasta e concluzia susținută de corpusul de referință
la data construirii datasetului" — nu „acesta e adevărul".

---

## 2. Arhitectura, pe componente

```
afirmație
   ↓  normalizare (diacritice, numere, entități, date)
   ↓  RETRIEVER      → top-k pasaje candidate din corpus     [BM25 → dense → hibrid]
   ↓  RERANKER       → reordonează top-50                    [opțional, S11]
   ↓  VERIFIER       → per pereche (claim, pasaj): SUPPORTS/REFUTES/NEI
   ↓  AGREGARE       → un verdict din mai multe pasaje, ponderat pe tier + dată
   ↓  CALIBRARE      → scor de încredere onest + prag pentru NEI
verdict + citate + explicație extractivă
```

Două modele antrenate **separat**: retriever (găsește dovada) și verifier (judecă
relația claim–dovadă). Se evaluează și separat, și end-to-end.

---

## 3. Deciziile de scope deja luate (nu se redeschid fără motiv)

| Subiect | Decizie | Motiv |
|---|---|---|
| Volum dataset | **650 gold** (220 SUP / 220 REF / 210 NEI) + 80 challenge | 1000 de claims = 130h din 240 doar adnotare |
| Domenii | Toate 5, cu ponderi inegale: economie 180, demografie 150, statistici RO/UE 120, administrație 110, legislație 90 | Volumul urmează costul de ingest, nu simetria |
| `MIXED` | Doar în split-ul `challenge`, niciodată clasă de antrenare | La 650 de claims, a 4-a clasă destabilizează macro-F1 |
| Corpus | **Unul singur**, comun tuturor split-urilor; se împart doar claims-urile | Corpusul nu conține etichete → nu e leakage |
| Demo | FastAPI + Streamlit, fără React | React e cosmetică |
| Experimente | 6, dintre care 3 cu seed-uri multiple | Restul → „future work" |
| Buget | 12 săptămâni × ~20h ≈ 240h | Planul detaliat: `RoFact_plan_executie.md` |

**Ce nu se taie sub nicio formă:** ground truth din surse primare, snapshot-uri cu
hash, split pe `family_id`, baseline lexical **și** baseline LLM-direct, comparația
clean vs. noisy cu seed-uri multiple, raportul final.

**Ordinea de tăiere dacă rămâi în urmă:** (1) reranker S11 → (2) FastAPI, rămâne doar
Streamlit → (3) experimentele 5 și 4 din S10 → (4) dataset 650→550 → (5) setul
challenge + `MIXED`.

---

## 4. Cele patru concepte care se înțeleg greșit cel mai des

### 4.1 „Noise"-ul din presă nu contaminează ground truth-ul
Sunt **trei straturi peste aceleași date**:
- **eticheta** vine exclusiv din G1/G2 — presa nu stabilește niciodată verdictul;
- **corpusul de căutare** amestecă oficial + media, ca retrieverul să lucreze într-un mediu realist;
- **perechile claim–pasaj** adnotează media pe două axe separate.

### 4.2 Cele două axe de adnotare (contribuția metodologică)
- `textual_relation` = **ce spune** pasajul: `SUPPORTS` / `REFUTES` / `MENTIONS` / `IRRELEVANT`
- `evidence_quality` = **cât valorează**: `GOLD_PRIMARY` / `CORROBORATIVE` / `UNVERIFIED` / `MISLEADING` / `OUTDATED`

Un articol poate avea `SUPPORTS` pentru o afirmație al cărei label e `REFUTED`.
**Nu e contradicție — e exact fenomenul studiat.** Regula încălcată cel mai des:
nu marca un pasaj `REFUTES` doar pentru că afirmația e falsă.

### 4.3 Snapshot
O copie înghețată a datelor la un moment fix + sha256 care dovedește ce ai descărcat.
Necesar pentru că INS și Eurostat se actualizează **în loc**, fără versionare
istorică. Manifestele se comit în git; datele brute nu.

### 4.4 `family_id` și leakage
Toate variantele aceleiași afirmații de bază (corectă + perturbate) au același
`family_id` și merg în **același split**. Fără asta: varianta corectă în train,
cea perturbată în test → modelul a văzut răspunsul → rezultatele nu înseamnă nimic.

---

## 5. Harta codului — ce e gata și ce nu

### Complet, funcțional
| Fișier | Ce face |
|---|---|
| `src/rofact/schemas.py` | Toate modelele Pydantic + invarianții ca reguli care resping datele greșite |
| `src/rofact/io.py` | JSONL tipizat, sha256, ID-uri deterministe, normalizare diacritice RO |
| `scripts/validate_data.py` | C1–C4 implementate (unicitate, integritate referențială, coerență etichetă/dovezi, media-niciodată-gold) |
| `docs/dataset_spec.md` | Ce conține datasetul și de ce |
| `docs/annotation_guide.md` | Definiții de etichete, toleranțe numerice, reguli temporale, un exemplu complet rezolvat |
| `docs/source_registry.md` | Note per sursă + tabelul de licențe |
| `configs/sources.yaml` | Registrul executabil al celor 9 surse |
| `tests/test_schemas.py` | 19 teste pe regulile datasetului |
| `.gitignore`, `requirements.txt`, `.github/workflows/ci.yml` | Infrastructură + CI |

### Schelet cu `raise NotImplementedError` — de scris
| Fișier | Funcții goale |
|---|---|
| `scripts/validate_data.py` | C5 leakage, C6 cvasi-duplicate, C7 echilibru clase, C8 diversitate perturbări, C9 acoperire ținte, C10 licențe/snapshot |
| `src/rofact/ingest/base.py` | `load_sources_config`, `check_robots` |
| `src/rofact/ingest/eurostat.py` | `fetch_dataset`, `iter_observations`, `observations_to_documents`, `extract_last_update` |
| `src/rofact/ingest/ins_tempo.py` | `fetch_tree`, `fetch_matrix_meta`, `parse_dimensions`, `fetch_matrix_data`, `data_to_documents`, `restore_diacritics` |
| `src/rofact/ingest/datagov.py`, `legislatie.py`, `pdf_docs.py` | tot |
| `src/rofact/passages.py` | `segment_document`, `segment_by_article`, `verbalize_table`, `format_number_ro`, `build_passages` |
| `scripts/build_corpus.py` | `run_ingest`, `main` |

### Nici măcar schelet (S6+)
`src/rofact/retrieval/`, `src/rofact/verify/`, `src/rofact/eval/`, `annotation/`,
`app/` — toate goale (doar `__init__.py` / `.gitkeep`).

---

## 6. Jurnal: ce am făcut, la ce probleme am dat, cum le-am rezolvat

### Sesiunile 1–2 (înainte de 2026-07-24) — planificare + schelet
**Făcut:** planul de execuție pe 12 săptămâni; specificația datasetului; ghidul de
adnotare; schemele Pydantic; io.py; validatorul C1–C4; registrul de surse; CI.
26 de fișiere, 19 teste care trec.

**Descoperiri la verificarea API-urilor:**
1. **INS TEMPO funcționează** și câmpurile `definitie` + `metodologie` din
   `/matrix/{cod}` sunt text narativ oficial → pasaje G1 gratuite, esențiale
   pentru claims despre confuzii de definiție (populație rezidentă vs. după domiciliu).
2. **TEMPO livrează text FĂRĂ DIACRITICE** („Populatia rezidenta"). Necesită
   normalizare la indexare, altfel BM25 nu potrivește „populația" cu „populatia".
   *Decizie recomandată:* fold_diacritics doar la indexare, nu modifica textul sursei.
3. **Verbalizarea tabelelor trebuie să folosească virgulă zecimală** („5,6" nu „5.6"),
   altfel potrivirea numerică eșuează sistematic exact pe categoria de claims care contează.
4. **Capcană Eurostat:** un cod de dimensiune invalid NU dă eroare HTTP — întoarce
   200 cu `value: {}` gol. Verifică întotdeauna că ai primit observații.

### Sesiunea 3 (2026-07-24) — reluare cu Claude Code
**Făcut:** audit complet al repo-ului; explicație de la zero a proiectului; crearea
acestui fișier de continuitate.

**Probleme identificate în mediu (de rezolvat înainte de a scrie cod):**
| Problemă | Detaliu | Rezolvare |
|---|---|---|
| Python greșit | `python` = 3.9.13. Pydantic v2 nu poate construi modelele cu sintaxă `str \| None` pe 3.9 → `schemas.py` crapă la import | Creează venv cu `py -3.11 -m venv .venv` (3.11 = versiunea din CI). 3.14 e prea nou pentru torch/faiss |
| Nimic nu e commit-uit | Tot repo-ul e untracked (`git status` = 13 directoare `??`) | Primul commit după ce trec testele |
| ~~Remote greșit~~ | ~~`origin` → `personal-project-fire-smoke-detector.git`~~ | ✅ REZOLVAT: `origin` → `https://github.com/mmandragiu/rofact.git` (repo redenumit pe GitHub). Pe remote, `main` = f271433 (doar README); scheletul nou e încă necommit-uit local |
| pytest nu e instalat | — | Vine cu `pip install -r requirements.txt` |

**Decizii:** —

---

## 7. Unde suntem

```
[####..........................................................] ~5% din proiect

S1  Specificație + infrastructură    ██████████░░  ~85%
S2  Surse primare (ingest API)       ███░░░░░░░░░  schelet gata, TODO-uri de scris
S3  Administrație/legislație/PDF     ░░░░░░░░░░░░
S4  Corpus media + unealtă adnotare  ░░░░░░░░░░░░
S5–S12                               ░░░░░░░░░░░░
```

### Ce urmează, în ordine

**Pasul 0 — mediu (30 min)**
```bash
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pytest tests/ -q            # trebuie 19 passed
git remote set-url origin <URL-ul repo-ului RoFact>
git add . && git commit -m "feat(s1): schemas, validator, spec și ghid de adnotare"
```

**Restul din S1 (~6h)**
1. Verifică licențele celor 9 surse, completează `docs/source_registry.md` (blocant pentru S2).
2. Scrie 5 exemple rezolvate per etichetă în `annotation_guide.md` §11.
3. Implementează C5 (leakage `family_id`) în `validate_data.py`.

**S2 (~22h)** — ordinea recomandată de implementare:
`validate_data.py` C5 → `passages.format_number_ro` → `eurostat.py` (API mai curat)
→ `passages.verbalize_table` → `ins_tempo.py` → `build_corpus.py`.

---

## 8. Riscurile de ținut minte

1. **Adnotarea (82h) e cel mai mare bloc.** Unealta Streamlit din S4 și generarea
   semi-automată sunt contramăsurile. *Checkpoint dur: dacă la finalul S7 ai sub
   350 de claims, cobori ținta la 550 și mergi mai departe.*
2. **Leakage prin `family_id`** — C5 din prima zi, nu la S10.
3. **Artefacte de perturbare** — niciun `perturbation_type` peste 40%.
4. **NEI prost definit** — cauza #1 de macro-F1 blocat sub 70%. Definiția operațională
   e în ghid §1: „snapshotul aprobat nu conține informația", nu „nu știu", nu „e ambiguu".

---

## 9. Fișierele de referință

| Fișier | Ce e |
|---|---|
| `C:\RoFact\RoFact_proiect.md` | Planul conceptual original |
| `C:\RoFact\RoFact_plan_pornire.md` | Varianta redusă ~110h (referință) |
| `C:\RoFact\RoFact_plan_executie.md` | **Planul de lucru activ**, ~240h, 12 săptămâni |
| `C:\RoFact\RoFact_rezumat_sesiuni.md` | Rezumatul sesiunilor 1–2 (înlocuit de fișierul de față) |
| `rofact/docs/stare_proiect.md` | **Documentul de față** — se actualizează la fiecare sesiune |
| `rofact/docs/journal.md` | Jurnal săptămânal formal → devine scheletul raportului final |

---

## 10. Convenția de limbă (decisă în sesiunea 3)

Proiectul e personal, pentru facultate, cu posibilă folosire ca portofoliu în
străinătate. Ambele scenarii trag spre engleză la stratul public, deci:

| Ce | Limbă |
|---|---|
| README, mesaje de commit, descrierea repo-ului | **engleză** |
| Nume de variabile/funcții/clase din cod | **engleză** (deja așa) |
| Comentarii + docstring-uri **noi** | **engleză** de acum înainte |
| Comentarii/docstring-uri existente în română | nu se retraduc acum; pass de curățenie la S12 |
| Data card / model card / raport final (S12) | **engleză** |
| Docs de lucru: `annotation_guide`, `journal`, `dataset_spec`, `stare_proiect` | română (unelte de lucru) |
| Exemplele de claims din docs | **română obligatoriu** (sistemul e despre limba română) |

---

## 11. Cum lucrez cu asistentul AI pe proiectul ăsta

Regula stabilită în sesiunea 3: **asistentul nu scrie codul integral.** Rolul lui e
să explice mecanismul, să scrie schelet/exemple parțiale, să revizuiască ce am scris
eu și să prindă bug-uri. Codul de producție îl scriu eu, ca să înțeleg ce face
proiectul. La finalul fiecărei sesiuni, asistentul actualizează §6 și §7 din
documentul acesta.
