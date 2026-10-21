# Team board
Lead: claude | Agents: claude, agy, copilot

| # | Task | Owner | Model | Worktree/branch | Status | Verified by |
|---|------|-------|-------|-----------------|--------|-------------|
| 1 | Data model, synthetic generator, API contract | claude | opus | master | merged | claude (seed + load checks) |
| 2 | analytics.py: EDA, hypothesis, regression, classification, clustering | agy | high | team/agy-analytics | merged | claude (21 tests + real-data run), copilot review |
| 3 | Frontend SPA (app/static) | copilot | high | team/copilot-frontend | failed -> rewritten by claude | claude (browser, light/dark/mobile) |
| 4 | Flask API, recommender engine, graph, ethics | claude | opus | master | merged | 11 API tests |
| 5 | Syllabus mapping docs + README | claude | opus | master | merged | claude |

## Notes / decisions
- Contract: docs/API_CONTRACT.md. Stack: Flask + SQLite + pandas/sklearn/scipy; vanilla JS frontend.
- Copilot frontend was minified one-line files, too thin for exam presentation; lead rewrote it.
- agy hit its timeout before committing; its working file passed all tests, so the lead committed it.
- Copilot review of agy branch flagged "deleted files" - false positive from diffing an older base against master.
- Lead fixes after merge: class_weight balanced, k>=3 personas, mean imputation for non-raters.
