# IEEE-style research report

Open `ieee_report.tex` in the Codex LaTeX editor or upload it to Overleaf. It is a standalone IEEEtran conference document: bibliography, tables, and three vector figures are embedded. No separate images or BibTeX file are required. A conventional TeX installation needs IEEEtran, TikZ, and PGFPlots; compile twice with pdfLaTeX to resolve references.

The author line uses only the supplied name, Vignesh. Add your institution, coauthors, and contact details before submission. No affiliation or publication acceptance is implied.

The report describes the social-media automation implementation, not the older ingress-moderation experiment. It uses the completed main, rephrased, and five ablation result files. It does not invent new trials, infer perfect detection from zero measured ASR, or claim measured parallel speedup.

`audit_results.py` checks saved row counts, duplicate keys, and agent-call aggregates, then creates `results_manifest.json` with raw-file SHA-256 hashes. It does not re-run inference or independently validate semantic outcome labels. Result files remain in the sibling `results` directory and may be gitignored; preserve them with any research archive.

Known evidence limitations are explicit in the manuscript: one observation per scenario and condition within each sweep, co-developed synthetic datasets, missing immutable historical run settings, incomplete cancelled-inference accounting, heuristic egress validation, weak factuality coverage in CSS, and large unexplained timing outliers.
