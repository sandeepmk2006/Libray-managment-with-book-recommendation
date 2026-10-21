# Athenaeum — Smart Library with Gate Analytics & Book Recommendations

A full-stack library system for a college library that does three things:

1. **Gate log** — every member scans in and out; the system knows who is inside, how long they stay, and when the floor gets busy.
2. **Reading insights** — exploratory analysis, statistical hypothesis tests, footfall forecasting, late-return prediction and reader segmentation on the gate and loan data.
3. **Book recommendations** — six recommender approaches (content-based, user/item collaborative filtering, matrix factorisation, popularity, and a diversity-aware hybrid), each with human-readable reasons and an offline evaluation scorecard.

It also includes a co-borrowing **network graph** (exportable to Neo4j) and a **privacy & fairness** audit.

> Built as the Internal Exam 3 project for **Data Science Ecosystem (23CS2024)** and its lab (23CS2025).
> See **[docs/SYLLABUS_MAPPING.md](docs/SYLLABUS_MAPPING.md)** for exactly which syllabus topic is used where.

## Run it

```bash
pip install -r requirements.txt
python run.py                 # first run generates data/library.db automatically
# open http://127.0.0.1:5000
```

Regenerate the dataset (different size or random seed):

```bash
python -m app.seed --members 320 --days 120 --seed 42
```

Run the tests:

```bash
pip install pytest
python -m pytest -q
```

## Using the app

| Page | What you can do |
|---|---|
| **Today** | Live numbers, arrivals by hour, who is inside right now, gate activity feed (auto-refresh) |
| **Gate** | Type or scan a member ID (e.g. `KU24000`). First scan = check in, next scan = check out with stay duration. "Send 8 readers through the gate" simulates traffic for a demo |
| **Discover** | Pick a member and compare six recommendation approaches; each pick shows *why*. Scorecard compares all approaches on held-out data |
| **Catalogue** | Search and filter 120 real books, issue a book to a member, see "readers also liked" |
| **Members** | Register, profiles with visit timeline, loans (mark returned), taste profile, personal picks |
| **Insights** | Usage patterns (EDA), hypothesis tests, footfall regression forecast, late-return classifiers with a live risk checker, reader personas (clustering) |
| **Reading web** | Interactive force-directed graph of books borrowed by the same readers; copy as Neo4j Cypher |
| **Privacy & fairness** | Pseudonymised export sample, k-anonymity, consent, fairness parity and disparate impact |

Shortcuts: `/` focuses search, `g` opens the gate, `Esc` closes drawers. Light and dark themes.

## Architecture

```
run.py                     Flask entry point
app/
  db.py                    SQLite schema + pandas loaders (load_frames)
  seed.py                  behaviour-driven synthetic data generator
  server.py                REST API (see docs/API_CONTRACT.md) + serves the SPA
  recommender.py           6 recommenders, explanations, MMR diversity, offline evaluation
  analytics.py             EDA, hypothesis tests, regression, classification, clustering
  graph.py                 co-borrowing graph + Neo4j Cypher export
  ethics.py                pseudonymisation, k-anonymity, fairness audit
  static/                  single-page frontend (vanilla JS modules, Chart.js, d3)
data/books.csv             catalogue of 120 real books with descriptions
tests/                     API + analytics tests (pytest)
docs/                      API contract, syllabus mapping
```

**Stack:** Python · Flask · SQLite · pandas · NumPy · SciPy · scikit-learn · Chart.js · d3.js

### About the data

The book catalogue is real. Members, visits, loans and ratings are **synthetic but behaviour-driven**: each member has hidden traits (department-driven genre taste, diligence, visit rate, preferred hour, stay length) and every record is *derived* from those traits, with exam-week rushes, weekend dips and ~7% deliberately missing values. That means the analytics have genuine patterns to find, and nothing about a real person is ever stored.
