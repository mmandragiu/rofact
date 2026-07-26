# Specificația datasetului RoFact — v1.0.0

Documentul definește **ce** conține datasetul și **de ce**. Regulile de adnotare
(cum decizi o etichetă) sunt în `annotation_guide.md`. Schemele executabile sunt
în `src/rofact/schemas.py` — acesta e documentul de referință; dacă cele două se
contrazic, codul câștigă și documentul se corectează.

---

## 1. Obiectiv

Un dataset românesc de verificare a afirmațiilor, în care corpusul de căutare
amestecă deliberat surse oficiale cu presă, pentru a răspunde experimental la:

> Cât de mult scade performanța unui fact-checker românesc când sursele oficiale
> sunt amestecate cu articole media incomplete, repetitive, vechi sau contradictorii?

---

## 2. Domenii și volume țintă

| Domeniu | Claims | Sursă principală |
|---|---:|---|
| economie | 180 | Eurostat, INS TEMPO, BNR |
| demografie | 150 | INS TEMPO, Eurostat |
| statistici_ro_ue | 120 | Eurostat |
| administratie_publica | 110 | data.gov.ro, rapoarte instituționale |
| legislatie | 90 | legislatie.just.ro |
| **Total gold** | **650** | |
| challenge (incl. `MIXED`) | 80 | toate |

**Distribuția etichetelor** (pe train+val+test): 220 `SUPPORTED` / 220 `REFUTED` /
210 `NOT_ENOUGH_INFO`, cu toleranță ±10%.

**Corpus:** 10.000–13.000 pasaje, din care 20–30% G1/G2, 10–20% secundare corecte,
50–60% media și distractori.

---

## 3. Fișierele datasetului

| Fișier | Model | Se comite în git |
|---|---|---|
| `data/processed/documents.jsonl` | `Document` | nu (regenerabil din snapshot) |
| `data/processed/passages.jsonl` | `Passage` | nu (regenerabil) |
| `data/annotations/claims.jsonl` | `Claim` | **da** |
| `data/annotations/claim_passage_pairs.jsonl` | `ClaimPassagePair` | **da** |
| `data/snapshots/manifests/{snapshot_id}.json` | `SnapshotManifest` | **da** |

Adnotările sunt produsul proiectului și se versionează. Corpusul se regenerează
din snapshot + manifest, deci nu îngroașă repo-ul.

---

## 4. Politica de ground truth

**Regula centrală:** eticheta unei afirmații provine **exclusiv** din dovezi G1/G2
aprobate manual.

| Tier | Ce e | Poate stabili eticheta? |
|---|---|---|
| G1 | date primare structurate (INS, Eurostat, data.gov.ro) | **da** |
| G2 | documente oficiale (rapoarte, legi, metodologii) | **da** |
| G3 | fact-check documentat (Factual.ro, AFP) | **nu** — doar descoperire |
| MEDIA | presă și surse secundare | **nu** — niciodată |

Validatorul impune regula automat (verificarea C4): un pasaj `MEDIA` sau `G3`
marcat `is_gold=True` e eroare, nu avertisment.

### Verdictul, formulat corect

> „Aceasta este concluzia susținută de corpusul de referință disponibil la data
> construirii datasetului."

Nu „acesta e adevărul".

---

## 5. Snapshot-uri și reproductibilitate

Bazele oficiale se actualizează **în loc**, fără versionarea valorilor istorice
(Eurostat o spune explicit în documentația API). O re-descărcare peste șase luni
poate da alte cifre pentru același an.

Prin urmare:

- fiecare descărcare produce o intrare în `SnapshotManifest`, cu URL, dată și sha256;
- `Document.content_hash` se calculează pe textul **normalizat** (`io.normalize_text`),
  ca o schimbare de spațiere să nu invalideze snapshotul;
- toate experimentele citează `snapshot_id`;
- manifestele se comit; datele brute nu.

---

## 6. Compunerea afirmațiilor

| Metodă | Pondere | Cum |
|---|---:|---|
| `real_claim` | ~40% | afirmații publice reale (declarații, articole, fact-check-uri G3), reformulate atomic fără a schimba sensul |
| `constructed` | ~40% | pornind de la o valoare primară, se produc manual variantele corectă / contrazisă / NEI |
| `hard` | ~20% | multi-evidence, comparative, dependente de dată, entități cu nume similare |

### `family_id`

Toate variantele derivate din aceeași valoare de bază primesc **același `family_id`**
și ajung în **același split**. Fără asta, varianta corectă în train și cea perturbată
în test = leakage, iar rezultatele tale nu înseamnă nimic.

### Diversitatea perturbărilor

`perturbation_type` e obligatoriu pentru `constructed`. Niciun tip nu poate depăși
**40%** din afirmațiile perturbate (verificarea C8). Altfel modelul învață tiparul
de formulare, nu faptul — și pare foarte bun până îl testezi pe afirmații reale.

Tipuri disponibile: `year_shift`, `value_shift`, `country_swap`, `comparison_flip`,
`negation`, `absolute_vs_percent`, `entity_swap`, `scope_shift`, `unit_swap`.

---

## 7. De ce `MIXED` nu se antrenează

`MIXED` există ca etichetă, dar apare **doar** în split-ul `challenge`:

1. la 650 de claims, o a patra clasă ar avea ~50 de exemple — prea puțin pentru a
   învăța ceva stabil, suficient pentru a destabiliza macro-F1;
2. `MIXED` e o proprietate a *granularității* afirmației, nu a lumii: o afirmație
   mixtă se poate sparge în două afirmații atomice. Ca sarcină de clasificare e
   prost pusă;
3. ca set challenge separat, devine o **analiză** interesantă („ce face sistemul
   când afirmația nu e atomică?") în loc de o clasă slabă.

Schema impune regula: `label=MIXED` cu `split != challenge` e eroare de validare.

---

## 8. Cele două axe de adnotare a pasajelor

`textual_relation` (ce spune pasajul) și `evidence_quality` (cât valorează) sunt
**independente**. Un pasaj media poate avea `SUPPORTS` pentru o afirmație
`REFUTED` — asta e corect și e exact fenomenul studiat.

Consecință de proiectare: `Claim.label` și `ClaimPassagePair.textual_relation`
**nu** trebuie să fie consistente între ele. Validatorul verifică doar că există
cel puțin un pasaj **gold** cu relația potrivită (C3), nu că toate pasajele o au.

---

## 9. Împărțirea datasetului

70% train / 15% val / 15% test, plus `challenge` separat.

Reguli obligatorii (verificate în C5–C7):

- un `family_id` = un singur split;
- claims-urile descoperite din același articol de fact-check merg în același split;
- cvasi-duplicatele se elimină **înainte** de split;
- orice augmentare se face **după** split;
- test set-ul se blochează la începutul S10 și nu se mai atinge;
- există un test „clean" și unul cu media noise;
- opțional: un test temporal, cu surse mai recente decât snapshotul de antrenare.

---

## 10. Ținte de acoperire

Verificate automat (C9), ca să nu descoperi lipsurile la S12:

- ≥ 200 claims cu valori numerice;
- ≥ 150 claims care necesită mai multe dovezi;
- ≥ 100 claims dependente de dată;
- ≥ 80 claims cu negație sau comparație;
- ≥ 80 claims unde un pasaj MEDIA are `SUPPORTS` iar eticheta e `REFUTED`
  (categoria cea mai valoroasă din dataset — miezul întrebării de cercetare);
- ≥ 20% din claims dublu-adnotate.

---

## 11. Ce NU conține datasetul (v1)

- sănătate, războaie, opinii politice, afirmații științifice specializate;
- interpretare juridică (doar fapte legislative literale — vezi ghidul, §7);
- afirmații despre persoane private;
- verdicte preluate automat de la platforme de fact-checking;
- afirmații generate de LLM fără revizuire manuală.

---

## 12. Limitări asumate

Se declară explicit în data card, nu se ascund:

1. **Adnotator preponderent unic.** ~20% dublu-adnotate; restul are o singură
   sursă de judecată. Sistematicitatea erorilor mele nu poate fi măsurată complet.
2. **Snapshot fix.** Sistemul nu știe nimic publicat după data snapshotului.
3. **Acoperire tematică inegală** între cele 5 domenii (vezi §2).
4. **Legislația e restrânsă** la fapte literale, deci nu reprezintă dificultatea
   reală a verificării afirmațiilor juridice.
5. **Corpusul media nu e un eșantion reprezentativ** al presei românești, ci o
   selecție construită pentru diversitate de tip și de comportament față de sursă.

---

## 13. Versionare

`SCHEMA_VERSION` în `src/rofact/schemas.py`. Orice modificare de schemă după
începerea adnotării se notează în `docs/journal.md` cu: ce s-a schimbat, câte
înregistrări au fost migrate, dacă a fost nevoie de re-adnotare.
