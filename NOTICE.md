# Notices

## Non-commercial project

The code in this repository is licensed under the PolyForm Noncommercial License 1.0.0
(see `LICENSE`). The evaluation data it is built around is licensed for non-commercial use
only (below). Nothing here may be used commercially.

## FinanceBench (CC BY-NC 4.0)

This project evaluates on the open-source sample of FinanceBench (Islam et al., 2023,
arXiv:2311.11944), published by Patronus AI under the Creative Commons
Attribution-NonCommercial 4.0 International license:

- Repository: https://github.com/patronus-ai/financebench
- Dataset card (states the license): https://huggingface.co/datasets/PatronusAI/financebench
- License text: https://creativecommons.org/licenses/by-nc/4.0/

How the data is handled here:

- No FinanceBench files (questions, answers, evidence text, PDFs) are committed.
  `scripts/download_financebench.py` downloads them from upstream commit
  `cc39aeb4afdf33909ee1412188bf89035950c2eb` into `data/raw/` (gitignored) and verifies
  each file against the SHA-256 digests in `data/financebench_manifest.json`.
- Changes made: the 150 questions are split into fixed dev and test sets
  (`data/splits/`, question IDs only), and additional labels written for this project
  (for example hand-labeled answer grades) are stored separately from the upstream files.
- Results derived from FinanceBench are reported for non-commercial research and
  educational purposes.

The financial filings themselves are public documents filed by the companies named in the
dataset.
