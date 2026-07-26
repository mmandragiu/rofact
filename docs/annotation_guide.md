# Ghid de adnotare RoFact — v0.1

> Documentul acesta e contractul cu tine însuți. Dacă la S7 te contrazici cu el, ori
> îl modifici explicit (și notezi în `journal.md` ce s-a schimbat și de ce), ori
> corectezi adnotarea. Ce nu ai voie e să adnotezi „după cum simți" — asta produce
> un dataset pe care niciun model nu poate învăța consistent.

**Versiune:** 0.1 (pre-pilot) · **Ultima revizie:** — · **Revizie obligatorie după pilotul din S5**

---

## 1. Cele patru etichete

### `SUPPORTED`
Snapshotul aprobat conține dovadă G1/G2 care confirmă afirmația, în limitele de toleranță de la §3.

### `REFUTED`
Snapshotul aprobat conține dovadă G1/G2 care contrazice afirmația. Contrazicerea trebuie să fie **directă**, nu dedusă prin raționament în mai mulți pași.

### `NOT_ENOUGH_INFO`
**Definiția operațională, singura acceptată:**

> Snapshotul aprobat **nu conține** informația necesară pentru a decide, deși afirmația este în principiu verificabilă.

`NOT_ENOUGH_INFO` **NU** înseamnă:

| Nu înseamnă | Ce faci în schimb |
|---|---|
| „nu știu / nu sunt sigur" | caută mai bine; dacă tot nu găsești, atunci da, e NEI |
| „e ambiguu ce vrea să spună" | reformulezi afirmația sau o arunci; ambiguitatea nu e o etichetă |
| „e parțial adevărat" | → `MIXED`, în challenge |
| „e o opinie" | **nu e claim** — afirmațiile neverificabile nu intră în dataset |
| „e prea complicat de verificat" | fie o simplifici, fie o arunci; nu ascunzi efortul sub NEI |

> **De ce contează atât:** NEI e clasa pe care modelele o greșesc cel mai des. Dacă cele ~210 exemple NEI ale tale înseamnă cinci lucruri diferite, verifier-ul nu are ce învăța și macro-F1 rămâne blocat sub 70%. Aceasta e cauza #1 de eșec în proiectele de tip FEVER.

### `MIXED` — doar în setul `challenge`
Afirmația conține elemente corecte **și** incorecte, separabile. Nu se antrenează pe ea; se raportează ca analiză.

*Exemplu:* „Șomajul a scăzut la 5,6% în 2023, cel mai mic nivel din istorie." — prima parte SUPPORTED, a doua REFUTED.

---

## 2. Este afirmația admisibilă? (filtrul de intrare)

Înainte de a eticheta orice, treci afirmația prin filtrul ăsta. Dacă pică la oricare, **nu intră în dataset**.

- [ ] Este **factuală**, nu o opinie sau o predicție.
- [ ] Conține **o singură idee principală** (atomică). Dacă are două, o spargi sau o trimiți la `MIXED`.
- [ ] Are **context temporal** suficient — explicit în text sau fixat prin `claim_date`.
- [ ] **Entitățile sunt neambigue** (ce țară, ce indicator, ce instituție, ce populație).
- [ ] **Unitatea de măsură** e determinabilă (procent / persoane / lei / euro / mii vs. milioane).
- [ ] Este verificabilă **din snapshot**, nu din cunoștințe generale.

---

## 3. Toleranțe numerice — fixate, nu negociabile

Fără regulile astea, aceeași afirmație primește etichete diferite la o săptămână distanță.

| Tip de valoare | Toleranță pentru `SUPPORTED` | Peste toleranță |
|---|---|---|
| Rate și procente (șomaj, inflație, sărăcie) | **± 0,2 puncte procentuale** | `REFUTED` |
| Valori absolute mari (populație, PIB, buget) | **± 1% relativ** | `REFUTED` |
| Numere mici, întregi (nr. de spitale, judeţe, articole de lege) | **exact** | `REFUTED` |
| Ani | **exact** | `REFUTED` |
| Formulări vagi („aproximativ 5%", „în jur de 20 de milioane") | ± 1 punct procentual / ± 5% relativ | `REFUTED` |

**Rotunjiri.** „Șomajul a fost de 6%" când INS zice 5,6% → diferența e 0,4pp > 0,2pp → **REFUTED**. Da, e sever. Consistența bate intuiția; alternativa e o zonă gri de sute de cazuri.

**Superlative și comparații** („cel mai mare din UE", „a scăzut față de anul trecut") se verifică **exact**, fără toleranță — ori ordinea e cea afirmată, ori nu.

**Zona gri.** Dacă valoarea cade în banda `toleranță` … `1,5 × toleranță`, marchează claim-ul cu `annotation_notes: "borderline"` și `annotator_confidence <= 0.7`. Le revizuiești în bloc la S9 și le poți muta în challenge.

---

## 4. Reguli temporale

- `claim_date` = **data la care afirmația se evaluează**, nu data la care a fost rostită. Dacă un politician spune în martie 2024 „șomajul e 5%", referința e anul 2023 (ultimul complet) → `claim_date = 2023-12-31`.
- Afirmație fără marcă temporală și fără context care s-o fixeze → **inadmisibilă**, nu NEI.
- O dovadă publicată **după** `claim_date` e acceptabilă (datele statistice apar cu întârziere), dar dacă e publicată după data la care afirmația a fost rostită, notează în `annotation_notes`.
- Valorile revizuite (INS revizuiește constant): folosești **valoarea din snapshot**, nu cea „adevărată azi". Verdictul înseamnă explicit „conform corpusului de referință la data construirii datasetului".

---

## 5. Adnotarea pasajelor — cele două axe

Pentru fiecare pereche afirmație–pasaj completezi **două câmpuri independente**. Aceasta e contribuția metodologică a proiectului; dacă le confunzi, dispare.

### Axa 1 — `textual_relation`: ce spune pasajul despre textul afirmației

| Valoare | Când |
|---|---|
| `SUPPORTS` | pasajul afirmă același lucru ca afirmația |
| `REFUTES` | pasajul afirmă ceva incompatibil cu afirmația |
| `MENTIONS` | pasajul aduce afirmația în discuție fără s-o probeze („X a declarat că…") |
| `IRRELEVANT` | pasajul nu se referă la afirmație |

### Axa 2 — `evidence_quality`: cât valorează ca dovadă

| Valoare | Când |
|---|---|
| `GOLD_PRIMARY` | sursă primară (G1/G2), suficientă singură |
| `CORROBORATIVE` | confirmă corect, dar nu e primară (ex. presă care citează corect INS, cu cifra exactă) |
| `UNVERIFIED` | afirmă fără a proba (declarații raportate, „potrivit unor surse") |
| `MISLEADING` | cifră scoasă din context, comparație nelegitimă, context esențial omis |
| `OUTDATED` | corect pentru anul lui, greșit pentru `claim_date` |

### Regula care se încalcă cel mai des

> **Nu marca un pasaj `REFUTES` doar pentru că afirmația e falsă.**

Un articol care repetă o cifră greșită **susține textual** afirmația. Relația e `SUPPORTS`; calitatea e `MISLEADING` sau `UNVERIFIED`. Eticheta afirmației rămâne `REFUTED`, stabilită de pasajul INS.

Dacă adnotezi ca `REFUTES` un pasaj care textual susține, antrenezi modelul să citească greșit. Validatorul nu poate prinde asta — doar tu poți.

---

## 6. Exemplu complet rezolvat

```
Afirmație:   „Rata șomajului în România a fost de 12% în 2023."
claim_date:  2023-12-31
topic:       economie
family_id:   somaj_romania_2023
creation:    real_claim

Dovadă INS (G1):
  „Rata șomajului în anul 2023 a fost de 5,6%."
  → textual_relation: REFUTES
  → evidence_quality: GOLD_PRIMARY
  → is_gold: True
  |12 - 5,6| = 6,4pp >> 0,2pp

Articol media A:
  „Un parlamentar a declarat că șomajul a atins 12%."
  → textual_relation: MENTIONS     (raportează o declarație, nu afirmă)
  → evidence_quality: UNVERIFIED
  → negative_type: repeats_claim_without_evidence

Articol media B:
  „Șomajul a urcat la 12%, arată cele mai recente cifre."
  → textual_relation: SUPPORTS     ← SUPPORTS, deși afirmația e falsă
  → evidence_quality: MISLEADING
  → negative_type: repeats_claim_without_evidence

Articol media C:
  „Rata șomajului în Spania a fost de 12,1% în 2023."
  → textual_relation: IRRELEVANT
  → evidence_quality: null
  → negative_type: wrong_country

Articol media D:
  „În 2013, rata șomajului era de 7,1%."
  → textual_relation: IRRELEVANT
  → evidence_quality: OUTDATED
  → negative_type: wrong_year

ETICHETA FINALĂ: REFUTED
annotator_confidence: 0.96
has_number: true   has_date: true
```

> **TODO (S1, 2h):** scrie încă **5 exemple rezolvate per etichetă**, câte unul din
> fiecare domeniu. Sunt cele care te salvează la S7 când nu mai ții minte
> convențiile. Pune-le în §11 de mai jos.

---

## 7. Reguli specifice pe domeniu

### Legislație — restricție deliberată
Se acceptă **doar** afirmații verificabile literal:

- existența / inexistența unui articol sau a unei prevederi;
- data intrării în vigoare sau a abrogării;
- un prag numeric explicit din text (cotă, termen, plafon);
- ce act a modificat ce act.

**Nu se acceptă:** „legea X înseamnă că…", „legea X permite…", orice cere interpretare. Dacă doi juriști ar putea fi în dezacord, afirmația nu intră.

### Demografie — capcana definițiilor
„Populația rezidentă" ≠ „populația după domiciliu" (INS publică ambele, cu diferențe de milioane). O afirmație care le confundă e `REFUTED` cu `perturbation_type: scope_shift`, iar pasajul de dovadă e definiția din `metodologie`, nu doar tabelul.

### Statistici comparative RO/UE
Trebuie să fie clar **ce se compară** (media UE-27? mediana? un anumit stat?) și **în ce unitate**. Fără asta → inadmisibilă.

---

## 8. Nivelul de încredere

| `annotator_confidence` | Când |
|---|---|
| 0,95 – 1,00 | dovadă primară directă, fără interpretare |
| 0,80 – 0,94 | dovadă solidă, cu un pas mic de raționament |
| 0,60 – 0,79 | borderline (vezi §3) sau multi-evidence cu o verigă slabă |
| < 0,60 | **nu eticheta** — mută în challenge sau aruncă |

---

## 9. Dublă adnotare și adjudecare

- Ținta: **20% din claims** dublu-adnotate.
- Ideal: al doilea om real pe ~80 de claims (coleg, prieten, profesor).
- Dacă nu găsești pe nimeni: **re-adnotare oarbă la minimum 10 zile**, fără să te uiți la eticheta anterioară — și **declari asta explicit în data card**. Un IAA de adnotator unic, declarat onest, e o limitare acceptată în cercetare. Unul pretins fals nu e.
- Raportează **Cohen's kappa**, nu doar procentul de acord.
- Dezacordurile se adjudecă și se marchează `adjudicated: true`. Notează în `journal.md` **de ce** au apărut — tipologia dezacordurilor e material bun pentru raport.

---

## 10. Checklist per afirmație

```
[ ] Trece filtrul de admisibilitate (§2)
[ ] claim_date fixat corect (§4)
[ ] family_id atribuit (toate variantele au același family_id)
[ ] Toleranța numerică aplicată conform §3
[ ] Dovezile provin DIN SNAPSHOT, nu dintr-o căutare web ad-hoc
[ ] Pasajele gold sunt suficiente FĂRĂ cunoștințe externe
[ ] Eticheta rezultă direct din dovezi, nu din ce știu eu
[ ] Pasajele media au relația textuală corectă, independent de etichetă (§5)
[ ] Am verificat dacă există o sursă mai apropiată de primar
[ ] creation_method + perturbation_type completate
[ ] has_number / has_date / has_negation / has_comparison bifate
[ ] annotator_confidence pus onest (§8)
```

---

## 11. Exemple rezolvate suplimentare

> **TODO (S1):** minimum 5 per etichetă, acoperind toate cele 5 domenii.
> Structura: afirmație → context → dovezi cu ambele axe → etichetă → de ce nu
> altceva. Ultima parte („de ce nu altceva") e cea mai utilă la recitire.

### SUPPORTED
1. *TODO — economie*
2. *TODO — demografie*
3. *TODO — statistici RO/UE*
4. *TODO — administrație publică*
5. *TODO — legislație*

### REFUTED
1. *(exemplul complet din §6)*
2. *TODO — demografie, scope_shift (rezident vs. domiciliu)*
3. *TODO — statistici RO/UE, comparison_flip*
4. *TODO — administrație publică*
5. *TODO — legislație, dată de intrare în vigoare greșită*

### NOT_ENOUGH_INFO
1. *TODO — indicator care nu e publicat la granularitatea cerută*
2. *TODO — an în afara seriei disponibile*
3. *TODO — defalcare teritorială inexistentă*
4. *TODO — administrație publică*
5. *TODO — legislație*

### MIXED (challenge)
1. *TODO — afirmație cu o parte corectă și un superlativ fals*
2. *TODO*

---

## 12. Jurnal de revizii

| Data | Versiune | Ce s-a schimbat | De ce |
|---|---|---|---|
| — | 0.1 | versiune inițială, pre-pilot | — |
| *TODO după S5* | 0.2 | | |
