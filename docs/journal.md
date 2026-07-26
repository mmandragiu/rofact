# Jurnal de lucru RoFact

Cinci rânduri la finalul fiecărei săptămâni. Nu e birocrație: la S12 acesta devine
scheletul raportului final și îți economisește ~4h de scris de la zero.

Format:

```
## S{n} — {perioada}   ({ore lucrate}h)
**Făcut:**
**Cifre:**        metrici obținute, dimensiuni de dataset — orice e măsurabil
**Blocat:**       ce nu a mers și de ce
**Decizii:**      ce am schimbat față de plan și motivul
**Urmează:**
```

Regula pentru „Decizii": orice abatere de la `RoFact_plan_executie.md` se scrie
aici **în momentul în care o iei**, nu retroactiv. Secțiunea „Limitări" a
raportului final se compune aproape integral din rândurile astea.

---

## S1 — {data}   ({}h)

**Făcut:**
- [ ] scaffold repo, `.gitignore`, `requirements.txt`
- [ ] `src/rofact/schemas.py` + `src/rofact/io.py`
- [ ] `scripts/validate_data.py` — C1–C4 implementate, C5–C10 de completat
- [ ] `configs/sources.yaml`
- [ ] `docs/dataset_spec.md`, `docs/annotation_guide.md`, `docs/source_registry.md`
- [ ] verificarea licențelor (tabelul din `source_registry.md`)
- [ ] 5 exemple rezolvate per etichetă în ghidul de adnotare
- [ ] CI: GitHub Action cu `validate_data.py` + `ruff`

**Cifre:**

**Blocat:**

**Decizii:**
- Domenii: toate 5, cu ponderi inegale (180/150/120/110/90). Motiv: acoperire
  tematică mai largă, asumând ~20h în plus la ingest și 650 claims în loc de 900.
- `MIXED` doar în challenge, nu ca a 4-a clasă de antrenare.

**Urmează:** S2 — ingest Eurostat + INS TEMPO.

---

## S2 — {data}   ({}h)

**Făcut:**

**Cifre:** documente: __ · pasaje: __ · din care verbalizate: __

**Blocat:**

**Decizii:**

**Urmează:**
