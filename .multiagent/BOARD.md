# Team board
Lead: claude | Agents: claude, agy, copilot

| # | Task | Owner | Model | Worktree/branch | Status | Verified by |
|---|------|-------|-------|-----------------|--------|-------------|
| 1 | Data model, synthetic generator, API contract | claude | opus | main | merged | claude |
| 2 | analytics.py: EDA, hypothesis, regression, classification, clustering | agy | high | team/agy-analytics | running | |
| 3 | Frontend SPA (app/static) | copilot | high | team/copilot-frontend | running | |
| 4 | Flask API, recommender engine, graph, ethics | claude | opus | main | running | |
| 5 | Syllabus mapping docs + README | claude | opus | main | todo | |

## Notes / decisions
- Contract: docs/API_CONTRACT.md. Stack: Flask + SQLite + pandas/sklearn/scipy; vanilla JS frontend.
