# Syllabus mapping — where each topic is used

**Courses:** Data Science Ecosystem (23CS2024, theory) and Data Science Ecosystem Lab (23CS2025)
**Project:** Athenaeum — library gate analytics and book recommendation system

Every topic below points to the file and function that implements it, and to the screen where it appears in the app.

---

## Module 1 — Basics of Data Science

| Syllabus topic | Where it is used |
|---|---|
| Introduction & applications of data science | The whole project is a data-science application: operational analytics (gate), prediction (late returns, footfall), personalisation (recommender) |
| Properties of data | Structured relational data (5 tables), time-series (gate log), text (book descriptions), graph (co-borrowing), explicit + implicit feedback (ratings vs loans). Schema in `app/db.py` |
| Exploring datasets in repositories | `data/books.csv`: a curated catalogue of 120 real books (title, author, genre, year, pages, description) |
| Tool boxes for data scientists | Python, pandas, NumPy, SciPy, scikit-learn, SQLite, Flask, Chart.js, d3.js, Neo4j (Cypher export) |

## Module 2 — Understanding Data

| Syllabus topic | Where it is used |
|---|---|
| Import | `app/db.py → load_frames()` reads SQLite tables into pandas DataFrames with `read_sql_query`; `seed.py` reads `books.csv` |
| Select / filter | `analytics.eda()`: closed visits only, returned loans only, opening hours 8–20; API search filters (`/api/books?q=&genre=`) |
| Manipulate | Derived columns: `duration_min`, `days_late`, `is_late`, hour, weekday, weekend flag; per-member feature tables |
| Sort / rank | Top borrowed books (`top_books`), genre popularity ranking, Bayesian-average popularity in `recommender._fit_popular` |
| Group / rearrange | `groupby` by department, purpose, genre, date, hour; 7×24 weekday-hour pivot (`weekday_hour`) |
| Missing data analysis | ~7% of visit purposes are deliberately missing; members with no ratings get mean imputation before clustering; per-table missing counts in `eda()["summary"]`; shown under **Insights → Usage patterns → Data quality** |
| Data visualisation (various plots) | Bar, line, histogram, doughnut, heatmap, radar, scatter, ROC curve, dendrogram, force-directed network, gauges. **Insights**, **Today**, **Discover**, **Reading web** |

## Module 3 — Statistical Inference

| Syllabus topic | Where it is used |
|---|---|
| Descriptive statistics: mean, median, variance, std dev | `analytics.eda()["describe"]` for stay duration, loans per member, rating, pages, days late (also quartiles, skew, kurtosis) → **Insights → Usage patterns → Summary statistics** |
| Small & large datasets | The same functions run on the 80-member test database (`tests/`) and on the full 16 000-visit dataset |
| Correlation between variables | Pearson correlation matrix of member-level features (`eda()["correlation"]`), plus Pearson & Spearman tests of visits vs loans |
| Exploratory data analysis | Hourly/weekday patterns, daily trend, stay distribution, IQR outlier detection, department comparison |
| Estimation | 95% confidence intervals (t-interval for means, Wilson interval for the late-return proportion) → **Insights → Questions & evidence** |
| Hypothesis testing (H₀ / H₁ for real-world cases) | `analytics.hypothesis()`. Each test states H₀, H₁, statistic, p-value, decision at α = 0.05, effect size and a plain-English interpretation:<br>• Do students stay longer on weekends? — Welch t-test<br>• Does stay length differ by department? — one-way ANOVA (η²)<br>• Is visit purpose independent of department? — χ² test (Cramér's V)<br>• Do frequent visitors borrow more? — Pearson & Spearman correlation<br>• Are first-years later with returns? — Mann-Whitney U<br>• Does the late-return rate differ by gender? — two-proportion z-test<br>• Are stay times normally distributed? — Shapiro-Wilk |

## Module 4 — Machine Learning

| Syllabus topic | Where it is used |
|---|---|
| Types of machine learning | Supervised regression (footfall), supervised classification (late returns), unsupervised clustering (personas), recommender learning (matrix factorisation) |
| Linear regression | `analytics.forecast()`: simple linear regression of hourly arrivals on time |
| Polynomial regression | `forecast()`: degree-3 polynomial on hour-of-day |
| Multiple regression | `forecast()`: hour, weekday, weekend, lag-24 and rolling-mean features (the best model; used for the 24-hour forecast) |
| Logistic regression | `analytics.classify()` and `predict_late()`: late-return prediction; coefficient × feature contributions explain each prediction |
| KNN | `classify()`: K-nearest neighbours with k tuned by cross-validation; user-based CF in `recommender.py` is also a KNN over users |
| Decision trees | `classify()`: depth-tuned tree, feature importances, rules printed with `export_text` → **Insights → Late returns** (+ random forest as an extension) |
| Similarity & distance measures | Cosine similarity (TF-IDF content, user-user, item-item), Euclidean distance (k-means), Ward linkage distance (agglomerative) |
| K-means clustering | `analytics.clusters()`: elbow (inertia) + silhouette to choose k, PCA projection to 2-D, auto-named reader personas |
| Agglomerative clustering | `clusters()`: Ward linkage, silhouette, adjusted Rand index agreement with k-means, dendrogram |
| Model evaluation | Chronological train/test split (forecast); stratified split + 5-fold CV, accuracy, precision, recall, F1, ROC-AUC, ROC curves, confusion matrices, class-weight balancing for the 38% minority class (classification); R², MAE, RMSE (regression); silhouette, ARI (clustering) |

## Module 5 — Recommender Systems

All in `app/recommender.py`; shown on **Discover**, **Catalogue** (readers also liked) and **Members**.

| Syllabus topic | Implementation |
|---|---|
| Content-based filtering | TF-IDF (unigrams + bigrams) over title, author, genre and description; a member's profile is the rating-weighted centroid of what they read; ranked by cosine similarity |
| Collaborative filtering (user-based) | Mean-centred cosine similarity between members, 30 nearest neighbours |
| Collaborative filtering (item-based) | Adjusted-cosine similarity between books |
| Model-based CF | Funk-SVD matrix factorisation with user/item biases, trained by stochastic gradient descent |
| Retail-style recommendation | Library loans act as purchases (implicit feedback, rating 3.5); explicit 1–5 ratings act as reviews |
| Hybrid recommenders | Weighted blend of all methods (weights tuned on hold-out NDCG), then **Maximal Marginal Relevance** re-ranking for variety; cold-start fallback uses department taste + popularity |
| Evaluating recommenders | `evaluate()`: per-member 20% hold-out, models retrained on training split only; Precision@10, Recall@10, NDCG@10, hit rate, catalogue coverage, intra-list diversity, RMSE → **Discover → scorecard** |

## Module 6 — Ethics in Data Science

All in `app/ethics.py`; shown on **Privacy & fairness**.

| Syllabus topic | Implementation |
|---|---|
| Privacy & confidentiality | Gate log stores only entry/exit time and optional purpose; no in-building tracking |
| Consent in data collection | `members.consent`: members who opt out receive only non-personalised picks (enforced in `Recommender.recommend`) |
| Anonymisation & de-identification | Salted SHA-256 pseudonyms, names dropped, timestamps coarsened to the hour, stay lengths banded, Neo4j export uses pseudonyms only |
| k-anonymity | Measured on (department, year, gender) before and after generalisation (year → cohort, department → school) and suppression |
| Bias & fairness | Gender is never a model feature (fairness through unawareness), then the outcome is still audited: favourable-outcome rate, true-positive rate and accuracy per group; disparate impact with the four-fifths rule; recommendation relevance parity across gender and department |
| Transparency, explainability, interpretability | Every recommendation shows its reasons; late-risk predictions show top contributing factors; decision-tree rules printed in plain text; model metrics published |
| Accountability | Evaluation protocols are documented in the UI and code, all randomness is seeded (reproducible), tests cover each module |

---

## Lab exercises (23CS2025)

| # | Exercise | Where |
|---|---|---|
| 1 | Introduction to data science with Python | Entire backend in Python |
| 2 | Working with data using Pandas, NumPy | `db.load_frames`, `seed.py` (NumPy random generators), `analytics.py`, `recommender.py` (NumPy matrices) |
| 3 | Exploratory data analysis | `analytics.eda()` → Insights › Usage patterns |
| 4 | Statistical inference | `analytics.hypothesis()` → Insights › Questions & evidence |
| 5 | Working with Neo4j | `graph.cypher_script()` exports `(:Member)-[:BORROWED]->(:Book)-[:IN_GENRE]->(:Genre)` and `CO_BORROWED` edges with example queries → Reading web › Copy as Neo4j Cypher |
| 6 | Data visualisation using Python libraries | Statistics computed with pandas/SciPy and rendered in the browser (Chart.js, d3) |
| 7 | Visualisation dashboard | The **Today** and **Insights** pages are live dashboards (in place of Tableau) |
| 8 | Performance analysis of regression | Insights › Footfall forecast: R², MAE, RMSE across three regressions |
| 9 | Performance analysis of classification | Insights › Late returns: accuracy, precision, recall, F1, ROC-AUC, confusion matrices |
| 10 | Tree-based classification | Decision tree + random forest, feature importance, printed rules |
| 11 | Working with NLP | TF-IDF vectorisation, stop-word removal, n-grams, cosine similarity of book descriptions; shared-theme terms in "readers also liked" explanations |
| 12 | Data acquisition from real-time systems | The gate: every scan is captured live, stored, and the dashboards refresh every 10 seconds |
