# paper-001 literature tooling

These scripts reproduce bounded discovery, source retrieval, and structural audit steps for the power-flow literature study. They do not generate substantive paper findings from metadata, train a model, or reproduce any published experimental results.

Use the workspace root. Install the recorded extraction dependency:

```powershell
python -m pip install -r papers/paper-001/configs/literature-requirements.txt
```

On a fresh clone only, initialize the local paper identity before using the workflow CLI:

```powershell
python paper.py restore --id paper-001 --title "AI用于电力系统潮流计算与分析"
python paper.py --paper paper-001 configure --direction "AI用于电力系统潮流计算与分析（Power Flow）"
```

Retrieval sequence (writes this paper's local literature directory):

```powershell
python papers/paper-001/scripts/collect_literature.py discover
python papers/paper-001/scripts/prepare_reading_batches.py
python papers/paper-001/scripts/collect_literature.py download --limit 150
python papers/paper-001/scripts/collect_crossref.py
```

The shortlist and Crossref date range are an explicit 2026-11-12 research snapshot. Re-running discovery against live indexes can change results and overwrites that run's discovery log; preserve the existing local study before a new search. arXiv requests are serial with a 3.2-second interval. A failed request is not a successful search. Raw response files and hashes are local provenance; ranking counts are not field-wide publication counts.

`retrieve_supplement.py <local-id> <https-pdf-url>` retrieves an explicitly selected supplemental PDF. A successful download does not mark it analyzed. Read the complete source and author a structured review in `literature/analysis-batches/<reader>/`. Source paths are relative to this paper; record eight substantive analysis fields and exact evidence locations. Review and resolve study families and cross-check corrections before registration:

```powershell
python papers/paper-001/scripts/finalize_corpus.py
python papers/paper-001/scripts/finalize_corpus.py --register
python paper.py --paper paper-001 corpus-audit
```

`finalize_corpus.py` checks authored records, registers them with the workspace API, binds source SHA-256, runs deduplication, and renders a local annotated catalogue. It rejects silently changed registered records. It cannot judge scientific entailment or replace reading/replication. Without local reviewed records it cannot recreate a passed literature gate.

Private full texts, research notes, literature reports, manuscript and raw logs are intentionally outside the GitHub publication allowlist. The remote contains the tooling, not a backup of those local research artifacts. Selection and experiments are separate later steps.
