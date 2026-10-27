"""Build the project report by editing the department's report template in place.

Every paragraph is cloned from a formatted paragraph of the template (headings, body
text, bullets, captions, tables, references), so fonts, sizes, spacing, indents,
alignment and auto-numbering stay identical to the required format.

Run:  python docs/build_report.py <template.docx> <output.docx>
"""
import copy
import json
import os
import re
import sys

import docx
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm
from docx.text.paragraph import Paragraph

HERE = os.path.dirname(os.path.abspath(__file__))
FIG = os.path.join(HERE, "figures")
R = json.load(open(os.path.join(FIG, "results.json")))

TEMPLATE, OUT = sys.argv[1], sys.argv[2]
PAGES = json.load(open(sys.argv[3])) if len(sys.argv) > 3 and os.path.exists(sys.argv[3]) else {}
d = docx.Document(TEMPLATE)
body = d.element.body
E = list(body.iterchildren())

# ------------------------------------------------------------ prototypes from the template
P_H1, P_H2, P_BODY, P_BULLET, P_BULLET_B = E[44], E[45], E[46], E[50], E[73]
P_CAPTION, P_TCAPTION, P_EQUATION, P_REF, P_SECT = E[81], E[122], E[85], E[143], E[99]
P_TABLE = E[121]


def _clear_runs(p):
    for child in list(p):
        if child.tag in (qn("w:r"), qn("w:bookmarkStart"), qn("w:bookmarkEnd"), qn("w:hyperlink")):
            p.remove(child)


def _run_like(proto_p, text, bold=None):
    """A run carrying the template's run formatting for this kind of paragraph."""
    rpr = None
    for r in proto_p.iter(qn("w:r")):
        if r.find(qn("w:t")) is not None:
            rpr = r.find(qn("w:rPr"))
            break
    r = docx.oxml.OxmlElement("w:r")
    if rpr is not None:
        rpr = copy.deepcopy(rpr)
        for sp in rpr.findall(qn("w:spacing")):
            rpr.remove(sp)
        for b in rpr.findall(qn("w:b")):
            rpr.remove(b)
        r.append(rpr)
    else:
        rpr = docx.oxml.OxmlElement("w:rPr")
        r.append(rpr)
    if bold:
        b = docx.oxml.OxmlElement("w:b")
        rpr.insert(0, b)
    t = docx.oxml.OxmlElement("w:t")
    t.text = text
    t.set(qn("xml:space"), "preserve")
    r.append(t)
    return r


def para(proto, parts):
    """Clone `proto` and fill it with parts: str or (text, bold)."""
    p = copy.deepcopy(proto)
    _clear_runs(p)
    for part in ([parts] if isinstance(parts, str) else parts):
        text, bold = (part, None) if isinstance(part, str) else part
        p.append(_run_like(proto, text, bold))
    return p


def numbered(proto, num_id, parts):
    p = para(proto, parts)
    p.find(qn("w:pPr")).find(qn("w:numPr")).find(qn("w:numId")).set(qn("w:val"), str(num_id))
    return p


# ------------------------------------------------------------ content builders
OUTPUT = []          # body elements in order
CH_NUM = {1: 6, 2: 7, 3: 8, 4: 9, 5: 10}   # chapter -> numbering list id in the template
state = {"ch": 0, "fig": 0, "tab": 0}


def section_break():
    OUTPUT.append(copy.deepcopy(P_SECT))


TOC_STRUCTURE = []


def chapter(n, title):
    TOC_STRUCTURE.append((n, title.title().replace("And", "and"), []))
    section_break()  # every chapter starts on a new page, as in the template
    state.update(ch=n, fig=0, tab=0)
    p = copy.deepcopy(P_H1)
    _clear_runs(p)
    ind = p.find(qn("w:pPr")).find(qn("w:ind"))
    ind.set(qn("w:left"), "1100"); ind.set(qn("w:right"), "1000")
    for a in ("hanging", "firstLine"):
        ind.attrib.pop(qn(f"w:{a}"), None)
    jc = p.find(qn("w:pPr")).find(qn("w:jc"))
    if jc is None:
        jc = docx.oxml.OxmlElement("w:jc"); p.find(qn("w:pPr")).append(jc)
    jc.set(qn("w:val"), "center")
    p.append(_run_like(P_H1, f"CHAPTER {n}"))
    br = docx.oxml.OxmlElement("w:r"); br.append(docx.oxml.OxmlElement("w:br")); p.append(br)
    p.append(_run_like(P_H1, title))
    OUTPUT.append(p)


def h2(text):
    TOC_STRUCTURE[-1][2].append(text)
    OUTPUT.append(numbered(P_H2, CH_NUM[state["ch"]], text))


def text(*parts):
    OUTPUT.append(para(P_BODY, list(parts)))


def bullets(items):
    for it in items:
        if isinstance(it, tuple):
            OUTPUT.append(numbered(P_BULLET_B, CH_NUM[state["ch"]], [(it[0] + ": ", True), it[1]]))
        else:
            OUTPUT.append(numbered(P_BULLET, CH_NUM[state["ch"]], it))


def equation(t):
    OUTPUT.append(para(P_EQUATION, t))


def figure(path, caption, width_cm=15.5):
    state["fig"] += 1
    p = para(P_BODY, "")
    OUTPUT.append(p)
    para_obj = Paragraph(p, d._body)
    para_obj.alignment = WD_ALIGN_PARAGRAPH.CENTER
    para_obj.paragraph_format.first_line_indent = 0
    para_obj.runs[0].add_picture(os.path.join(FIG, path), width=Cm(width_cm))
    OUTPUT.append(para(P_CAPTION, f"Figure {state['ch']}.{state['fig']}: {caption}"))


def table(header, rows, widths, caption):
    """Table in the template's style: fixed layout, single black borders, TNR 10.5 pt."""
    state["tab"] += 1
    t = copy.deepcopy(P_TABLE)
    grid = t.find(qn("w:tblGrid"))
    for g in list(grid):
        grid.remove(g)
    for w in widths:
        gc = docx.oxml.OxmlElement("w:gridCol"); gc.set(qn("w:w"), str(w)); grid.append(gc)
    proto_rows = t.findall(qn("w:tr"))
    head_cell, body_cell = proto_rows[0].findall(qn("w:tc"))[1], proto_rows[1].findall(qn("w:tc"))[1]
    tr_head, tr_body = proto_rows[0], proto_rows[1]
    for r in proto_rows:
        t.remove(r)
    tbl_ind = t.find(qn("w:tblPr")).find(qn("w:tblInd"))
    tbl_ind.set(qn("w:w"), str(max(0, (9500 - sum(widths)) // 2)))

    def make_row(proto_tr, proto_tc, cells, bold):
        tr = copy.deepcopy(proto_tr)
        for tc in tr.findall(qn("w:tc")):
            tr.remove(tc)
        for i, (val, w) in enumerate(zip(cells, widths)):
            tc = copy.deepcopy(proto_tc)
            tc.find(qn("w:tcPr")).find(qn("w:tcW")).set(qn("w:w"), str(w))
            p = tc.find(qn("w:p"))
            _clear_runs(p)
            ppr = p.find(qn("w:pPr"))
            jc = ppr.find(qn("w:jc"))
            if jc is None:
                jc = docx.oxml.OxmlElement("w:jc"); ppr.append(jc)
            jc.set(qn("w:val"), "left" if i == 0 else "center")
            ind = ppr.find(qn("w:ind"))
            if ind is not None:
                ind.set(qn("w:left"), "100")
            p.append(_run_like(p, str(val), bold=bold))
            tr.append(tc)
        return tr

    t.append(make_row(tr_head, head_cell, header, True))
    for row in rows:
        t.append(make_row(tr_body, body_cell, row, False))
    OUTPUT.append(t)
    cap = para(P_TCAPTION, f"Table {state['ch']}.{state['tab']}: {caption}")
    cap.find(qn("w:pPr")).find(qn("w:ind")).set(qn("w:left"), "0")
    cap.find(qn("w:pPr")).find(qn("w:jc")).set(qn("w:val"), "center")
    OUTPUT.append(cap)


def f3(x):
    return f"{x:.3f}"


# ============================================================================ CONTENT
m = R["rec"]
ctx_gain = (m["context"]["ndcg"] / m["hybrid"]["ndcg"] - 1) * 100
fc = {n: (r2, mae, rmse) for n, r2, mae, rmse in R["forecast"]}
cls = {c[0]: c for c in R["classify"]}
n_vis, n_loans, n_rat = R["counts"]["visits"], R["counts"]["loans"], R["counts"]["ratings"]

# ---------------------------------------------------------------- abstract (keeps template heading)
abstract = [
    "A college library collects useful data every day: who walks in, how long they stay, which books they "
    "take home and how they rate them. In most institutions this data sits in a paper register or an "
    "isolated issue-return system and is never analysed. Students therefore struggle to discover books "
    "that suit them, librarians cannot anticipate crowding, and late returns are noticed only after the "
    "due date.",
    "This project presents Athenaeum, a smart library system that joins three parts into one data science "
    "pipeline: a live entry and exit gate, an analytics layer, and a book recommender. The book catalogue "
    f"is web-scraped from the Open Library API: 1,980 candidate records were collected across 18 genres and "
    "cleaned to 510 English titles with real descriptions, community ratings and reading-demand counts. "
    f"Gate visits ({n_vis:,}), loans ({n_loans:,}) and ratings ({n_rat:,}) for 600 members are captured by the "
    "gate and issue desk, simulated for this study from documented behavioural assumptions.",
    "The analytics layer applies exploratory data analysis, eight hypothesis tests, three regression models "
    "for footfall forecasting, four classifiers for late-return prediction, and k-means and agglomerative "
    "clustering for reader segmentation. The main contribution is a gate-context-aware hybrid recommender: "
    "it learns from the gate log how a member’s typical visit length relates to the length of books they "
    "borrow, and re-weights a hybrid of content-based and collaborative filtering accordingly. On held-out "
    f"loans it improves NDCG@10 from {f3(m['hybrid']['ndcg'])} to {f3(m['context']['ndcg'])} "
    f"({ctx_gain:.0f}% relative gain) over the plain hybrid. A second contribution combines the footfall "
    "regression with the measured stay-time distribution to forecast hourly occupancy and warn staff before "
    "the reading room fills.",
    "All results are shown in a web application built with Flask, Chart.js and d3.js, and every model is "
    "paired with explanations, a privacy audit (pseudonymisation and k-anonymity) and a fairness audit.",
]
keywords = ("Keywords: ", "Web Scraping, Exploratory Data Analysis, Hypothesis Testing, Regression, Classification, "
            "Clustering, Context-Aware Recommender System, Hybrid Filtering, Data Ethics")

# ---------------------------------------------------------------- chapter 1
chapter(1, "INTRODUCTION")
h2("Background of the Project")
text("Libraries are one of the few places on a campus where student behaviour is recorded continuously. An "
     "entry register shows when the building is busy, the issue desk shows which subjects are in demand, and "
     "return dates show how reliable borrowers are. Data science gives a library the tools to turn these "
     "records into decisions: descriptive statistics summarise usage, inference tells real effects apart "
     "from chance, machine learning predicts what will happen next, and recommender systems match each "
     "reader with books they are likely to value.")
text("Recommender systems are well established in online retail and streaming, yet library catalogues are "
     "still mostly searched by title or subject. A library also knows something an online shop does not: "
     "how each reader physically uses the space. A student who settles in for three hours behaves "
     "differently from one who drops in for twenty minutes between classes, and this context can shape what "
     "a good recommendation is.")
h2("Problem Statement")
text("Most college libraries record entries on paper or in a stand-alone system, so occupancy, visit "
     "patterns and borrowing behaviour are never analysed together. Students find books only by browsing or "
     "by word of mouth, staff learn that the reading room is full only when it is full, and overdue books "
     "are discovered after the fact. There is no single system that captures live gate data, analyses it "
     "with sound statistical methods, and uses it to recommend books in a transparent and fair way.")
h2("Objectives")
bullets([
    "Build a web scraper that collects a real, cleaned book catalogue from the Open Library API.",
    "Record live entry and exit events and show current occupancy and visit durations.",
    "Explore the data with descriptive statistics and test real questions with hypothesis tests.",
    "Forecast hourly footfall and occupancy, and predict late returns before a book is issued.",
    "Group members into reader personas using unsupervised clustering.",
    "Design a gate-context-aware hybrid recommender and evaluate it against standard methods.",
    "Protect member privacy and audit every model for fairness and explainability.",
])
h2("Scope of the Project")
text("The system targets a single college library with a reading room of 60 seats and a catalogue of a few "
     "hundred titles. It covers data acquisition (scraping and gate capture), storage, analysis, prediction, "
     "recommendation and presentation through a browser. Member activity is generated from documented "
     "behavioural assumptions because real student records cannot be shared; the same code runs unchanged "
     "on real gate and loan records. Physical card-reader hardware is outside the scope: the gate accepts "
     "an ID typed or sent by any scanner that behaves like a keyboard.")

# ---------------------------------------------------------------- chapter 2
chapter(2, "LITERATURE SURVEY")
h2("Review of Existing Research")
OUTPUT.append(para(P_BODY, [
    ("Content-based filtering ", True),
    "represents items by their text and recommends items similar to those a user liked; TF-IDF weighting "
    "(Salton and Buckley, 1988) remains the standard representation. ",
    ("Collaborative filtering ", True),
    "uses the behaviour of many users instead: item-based CF (Sarwar et al., 2001) compares items through "
    "the users who rated them, while matrix factorisation (Koren et al., 2009) learns latent taste factors. ",
    ("Hybrid recommenders ", True),
    "combine both to offset each other’s weaknesses such as cold start and sparsity (Burke, 2002; Bobadilla "
    "et al., 2013). ",
    ("Context-aware recommenders ", True),
    "add information about the situation of the user, such as time, location or companion "
    "(Adomavicius and Tuzhilin, 2011), and ",
    ("diversity re-ranking ", True),
    "with Maximal Marginal Relevance (Carbonell and Goldstein, 1998) avoids lists made of near duplicates.",
]))
text("For evaluation, ranking quality is usually measured with precision, recall and normalised discounted "
     "cumulative gain (Järvelin and Kekäläinen, 2002) on held-out interactions. On the ethics side, "
     "k-anonymity (Sweeney, 2002) measures re-identification risk, and the disparate-impact ratio "
     "(Feldman et al., 2015) is a common test of group fairness; both are central to responsible data "
     "science practice (Martens, 2022).")
h2("Summary of Existing Approaches")
text("Existing library systems fall into three groups: integrated library management systems that handle "
     "cataloguing and circulation but do no analysis; footfall counters and RFID gates that report "
     "occupancy but are not linked to borrowing; and generic recommenders that suggest popular or "
     "similar books from loan history alone. Each solves one part of the problem in isolation.")
h2("Research Gap")
text("The review shows that the physical behaviour of library users is ignored by book recommenders, and "
     "that gate data is rarely used for anything beyond head counts.")
bullets([
    ("Context is unused", "no recommender uses how long or how often a member visits the library."),
    ("Occupancy is reactive", "staff see crowding when it happens instead of being warned in advance."),
    ("Decisions are opaque", "recommendations and risk scores are rarely explained or checked for fairness."),
])

# ---------------------------------------------------------------- chapter 3
chapter(3, "METHODOLOGY AND SYSTEM DESIGN")
h2("Proposed Methodology")
text("The project follows the complete data science workflow, from acquiring data to deploying explained "
     "results. Each stage is a separate Python module so it can be tested on its own.")
bullets([
    ("Acquisition", "scrape the Open Library search and work APIs; capture gate scans, loans and ratings."),
    ("Cleaning", "remove duplicates, non-English editions, mislabelled genres and empty descriptions."),
    ("Exploration and inference", "descriptive statistics, missing-value analysis, correlation and hypothesis tests."),
    ("Modelling", "regression for footfall, classification for late returns, clustering for personas."),
    ("Recommendation", "seven recommenders, including the proposed gate-context-aware hybrid."),
    ("Evaluation and ethics", "held-out testing, cross-validation, privacy and fairness audits."),
])
figure("workflow.png", "End-to-end workflow of the Athenaeum pipeline")
h2("Dataset and Web Scraping")
text("The catalogue is collected by app/scraper.py. For each of 18 genres the scraper queries the Open "
     "Library search API by subject, sorted by reading-log activity, and keeps the title, author, first "
     "publication year, median page count, community rating, rating count and want-to-read count. It then "
     "visits each work page to scrape the description. Requests are rate-limited, identified with a "
     "User-Agent header and retried with exponential back-off, and a raw JSON snapshot is saved for "
     "reproducibility.")
text("Crowd-sourced subject tags are noisy, so the cleaning step removes duplicate works and titles, keeps "
     "only English editions, drops novels tagged with non-fiction subjects (for example a cyberpunk novel "
     "tagged “computers”), and discards records without a usable description. Narrow genres are processed "
     "first so that a book listed under several subjects keeps its most specific genre.")
table(["Stage", "Records", "Notes"],
      [["Scraped candidates", "1,980", "18 genres, up to 90 per subject"],
       ["After cleaning", "510", "English, de-duplicated, genre-checked"],
       ["With description", "508", "scraped from work pages"],
       ["Median pages / rating", f"{int(R['scrape']['pages_median'])} / {R['scrape']['rating_mean']:.2f}", "Open Library community data"],
       ["Gate visits", f"{n_vis:,}", "600 members, 120 days"],
       ["Loans / ratings", f"{n_loans:,} / {n_rat:,}", "issue desk records"]],
      [2700, 1500, 4200], "Dataset summary")
figure("scrape_genres.png", "Scraped catalogue by genre after cleaning", 12.5)
text("Gate visits, loans and ratings are generated by app/seed.py from member traits such as department "
     "taste, diligence, visit rate and usual stay length. Real Open Library demand and ratings are used as "
     "priors, about 7% of visit purposes are left missing on purpose, and exam weeks and weekends change "
     "behaviour, so the analysis works on realistic, imperfect data.")
h2("System Architecture")
text("The system has four layers. Data enters from the scraper and the gate; it is stored in SQLite; the "
     "Python engine (pandas, NumPy, SciPy and scikit-learn) computes statistics, models and "
     "recommendations; and a Flask REST API serves a single-page web application that draws charts with "
     "Chart.js and d3.js.")
figure("architecture.png", "System architecture of Athenaeum")
h2("Algorithms and Workflow")
OUTPUT.append(para(P_BODY, [
    ("Hybrid recommender: ", True),
    "content-based TF-IDF similarity, user-based and item-based collaborative filtering, matrix "
    "factorisation and popularity are each normalised to 0–1 and blended with weights tuned on hold-out "
    "NDCG:",
]))
equation("Hybrid(u, i) = 0.55·Content + 0.15·ItemCF + 0.15·UserCF + 0.05·MF + 0.10·Popularity")
OUTPUT.append(para(P_BODY, [
    ("Proposed gate-context re-weighting: ", True),
    "from the gate log, each member’s median stay s is related to the typical length of the books they "
    "borrow by a log-log regression, log p̂ = a·log s + b. Each book of length p then receives a length-fit "
    "score and the hybrid score is re-weighted:",
]))
equation("Fit(u, i) = exp( −(log p_i − log p̂_u)² / 2σ² ),   Score = Hybrid · (0.7 + 0.3·Fit)")
text(f"On this dataset the regression gives a = {R['ctx'][0][0]:.2f} with a correlation of "
     f"r = {R['ctx'][1]:.2f}. The context strength (0.3) was chosen on a separate validation split, and the "
     "final list is re-ranked with Maximal Marginal Relevance so it covers several themes. Because the "
     "length fit needs only gate data, it also personalises results for members who have visited but never "
     "borrowed.")
OUTPUT.append(para(P_BODY, [
    ("Occupancy forecast: ", True),
    "the best footfall regression predicts arrivals A for each coming hour, and the empirical survival "
    "function S(t) of stay length gives the share of visitors still inside after t hours:",
]))
equation("Occupancy(h) = Inside_now · S(h) + Σ_j A_j · S(h − j + ½)")
text("An alert is raised when the forecast exceeds 70% of the 60 seats and a stronger alert above 90%.")
h2("Tools and Technologies Used")
text("The project uses free, open-source tools only: Python 3.10; requests for web scraping; pandas and "
     "NumPy for data handling; SciPy for statistical tests; scikit-learn for regression, classification, "
     "clustering and TF-IDF; SQLite for storage; Flask for the REST API; Chart.js and d3.js for "
     "visualisation; Matplotlib for report figures; pytest for automated testing; and Git and GitHub for "
     "version control. The co-borrowing graph can be exported as Cypher for Neo4j.")
h2("Module Description")
bullets([
    ("scraper.py", "collects and cleans the Open Library catalogue."),
    ("seed.py and db.py", "define the schema and generate behaviour-driven member activity."),
    ("analytics.py", "EDA, hypothesis tests, footfall and occupancy forecasts, classifiers and clustering."),
    ("recommender.py", "seven recommenders, explanations, MMR re-ranking and offline evaluation."),
    ("ethics.py and graph.py", "pseudonymisation, k-anonymity, fairness audit and the Neo4j export."),
    ("server.py and static/", "the Flask API and the browser application."),
])

# ---------------------------------------------------------------- chapter 4
chapter(4, "IMPLEMENTATION AND RESULTS")
h2("Implementation Details")
text("The application is started with python run.py and opened at http://127.0.0.1:5000. On start-up a "
     "background thread trains the recommenders and analytics models so that pages respond in well under a "
     "second; models are cached and retrained after many new loans. The gate treats the first scan of an ID "
     "as an entry and the next as an exit, and a capacity check refuses entry when the reading room is full.")
h2("Screenshots of the Application")
figure("gate.png", "Gate kiosk recording a check-in")
text("Typing or scanning a member ID records an entry or an exit; the stamp shows the member, the time and, "
     "on exit, the length of the visit. The occupancy gauge updates immediately.")
figure("today_crop.png", "Live overview with occupancy forecast and crowding alerts", 14.5)
figure("discover.png", "Recommendations from the proposed method with their reasons")
text("Every recommendation carries plain-language reasons, for example the book it is anchored on, how its "
     "length suits the member’s usual visit, and how similar readers rated it.")
h2("Exploratory Analysis and Hypothesis Testing")
ds = R["describe"]["duration_min"]
text(f"Visit length is right-skewed: the mean stay is {ds['mean']:.1f} minutes, the median {ds['median']:.1f} "
     f"minutes and the standard deviation {ds['std']:.1f} minutes (skewness {ds['skew']:.2f}). Arrivals peak in "
     "the late morning and mid-afternoon, and missing visit purposes are reported as “Not recorded” "
     "rather than guessed.")
figure("eda_crop.png", "Usage patterns: weekday-hour heatmap, daily visits and stay distribution", 14.5)
rows = []
for q, test, stat, p, dec, eff in R["tests"]:
    rows.append([q.rstrip("?"), test.replace(" test of independence", ""), "< 0.001" if p < 0.001 else f"{p:.3f}",
                 "Reject H0" if dec.startswith("Reject") else "Fail to reject"])
table(["Question", "Test", "p-value", "Decision"], rows, [4300, 2400, 1150, 1600],
      "Hypothesis tests on the library data")
text("Frequent visitors borrow more books, first-year students return books later than seniors, and mean "
     "stay differs across departments. Weekday and weekend stays do not differ, and the gender difference "
     "in late returns is not significant at the 5% level. 95% confidence intervals: mean stay "
     f"{R['ci'][0]['low']:.1f}–{R['ci'][0]['high']:.1f} minutes, late-return rate "
     f"{R['ci'][2]['low']:.3f}–{R['ci'][2]['high']:.3f}.")
h2("Regression and Classification Results")
table(["Footfall model", "R²", "MAE", "RMSE"],
      [[n, f3(v[0]), f"{v[1]:.2f}", f"{v[2]:.2f}"] for n, v in fc.items()],
      [3800, 1400, 1400, 1400], "Hourly footfall forecast on the last 14 days")
text("A straight trend line cannot follow the daily rise and fall of arrivals, so it scores below zero. A "
     "polynomial in the hour of day captures the shape, and multiple regression that also uses the weekday, "
     "weekend flag and the count 24 hours earlier explains most of the variation; it drives the occupancy "
     "forecast.")
table(["Late-return classifier", "Accuracy", "Precision", "Recall", "F1", "ROC-AUC"],
      [[c[0], f3(c[1]), f3(c[2]), f3(c[3]), f3(c[4]), f3(c[5])] for c in R["classify"]],
      [2600, 1300, 1300, 1150, 1050, 1300], "Late-return prediction on the test set")
fi = ", ".join(f["feature"].replace("_", " ") for f in R["fi"][:3])
text(f"Of {R['balance']['late'] + R['balance']['on_time']:,} returned loans, "
     f"{R['balance']['late'] / (R['balance']['late'] + R['balance']['on_time']) * 100:.0f}% were late. "
     "Features use only what is known at issue time, classes are balanced with class weights, and K and the "
     f"tree depth are tuned by cross-validation. The strongest predictors are {fi}. Logistic regression "
     "gives the best balance of recall and F1 and also explains each prediction through its coefficients.")
figure("model_compare.png", "Regression and classification model comparison")
h2("Reader Personas")
pers = "; ".join(f"{p} ({n})" for p, n in R["clusters"]["p"])
text(f"K-means on eight behaviour features, with k chosen by the elbow and silhouette methods, gives "
     f"{R['clusters']['k']} personas: {pers}. Agglomerative clustering with Ward linkage gives a similar "
     f"grouping (adjusted Rand index {R['clusters']['agg']['agreement_ari']:.2f}).")
figure("personas_crop.png", "Reader personas, PCA map and choice of k", 14.5)
h2("Recommender Evaluation")
names = {"context": "Gate-context hybrid (proposed)", "hybrid": "Hybrid", "content": "Content-based",
         "user_cf": "User-based CF", "item_cf": "Item-based CF", "svd": "Matrix factorisation",
         "popular": "Popularity"}
table(["Method", "NDCG@10", "Recall@10", "Hit rate", "Coverage"],
      [[names[k], f3(v["ndcg"]), f3(v["recall"]), f3(v["hit_rate"]), f3(v["coverage"])] for k, v in m.items()],
      [3300, 1350, 1350, 1350, 1350], f"Offline evaluation on held-out loans of {R['rec_users']} members")
text("For every member with at least five books, 20% of their books are hidden, all models are retrained "
     "without them, and each model’s top ten list is checked for the hidden books. The proposed method "
     f"achieves the best NDCG@10 ({f3(m['context']['ndcg'])} against {f3(m['hybrid']['ndcg'])} for the plain "
     f"hybrid, a {ctx_gain:.0f}% relative gain) while keeping list diversity high. Absolute scores are low "
     "because a member reads only a few of 510 titles, which is normal for top-N evaluation; the "
     "comparison between methods is what matters.")
figure("rec_compare.png", "NDCG@10 and recall of the seven recommenders")
figure("context_fit.png", "Gate context: median stay against the length of borrowed books", 12)
h2("Privacy and Fairness Results")
text("Member IDs are replaced by salted SHA-256 tokens, names are dropped and times are rounded to the hour "
     "in every export. On department, year and gender the smallest group in the raw data holds only "
     f"{R['ethics']['k_raw']} people (k = {R['ethics']['k_raw']}); after year becomes Junior or Senior and department becomes its "
     f"school, every group holds at least {R['ethics']['k_after']} people. Gender is never a model feature, yet the late-return "
     f"model is still audited per group: its disparate-impact ratio is {R['ethics']['di']:.2f}, which passes the four-fifths "
     f"rule. The {R['ethics']['opted_out']} members who opted out receive only non-personal recommendations.")
figure("trust_crop.png", "Privacy and fairness audit page", 14.5)
h2("Testing and Results")
text("An automated pytest suite of 36 tests covers the scraper’s cleaning rules, every API endpoint, the "
     "gate entry and exit cycle, the loan cycle, all seven recommenders, the evaluation, the occupancy "
     "forecast, the ethics report and every analytics function. All tests pass.")

# ---------------------------------------------------------------- chapter 5
chapter(5, "CONCLUSION AND FUTURE ENHANCEMENT")
h2("Summary of the Work")
text("A real book catalogue was scraped and cleaned from Open Library, a live gate and issue desk were "
     "built, and the resulting data was explored, tested and modelled with the methods of the data science "
     "ecosystem. A new gate-context-aware recommender and an occupancy forecast were designed, implemented "
     "and evaluated, and every result is presented through an explained, privacy-aware web application.")
h2("Conclusion")
text("The project shows that the way people use a library building is useful information for recommending "
     "books. Re-weighting a hybrid recommender by how well a book’s length suits a member’s usual visit "
     f"improved ranking quality by {ctx_gain:.0f}% over a strong hybrid baseline, and it personalises results "
     "for members with no borrowing history. Combining footfall regression with the stay-time distribution "
     "turns a head count into an advance warning of crowding. Throughout, explanations, k-anonymity and "
     "fairness checks keep the system transparent and accountable.")
h2("Limitations and Future Enhancements")
text("Member activity in this study is simulated from stated assumptions, including the link between stay "
     "length and book length, so the size of the gain should be confirmed on real gate and loan records.")
bullets([
    "Validate the gate-context method on real library data and add time-of-day context.",
    "Connect a physical RFID or barcode reader to the gate endpoint.",
    "Scrape further sources such as Google Books for more descriptions and cover images.",
    "Learn the hybrid and context weights per member instead of globally.",
    "Send crowding alerts and due-date reminders by e-mail or messaging apps.",
])

# ---------------------------------------------------------------- references
REFS = [
    "L. Igual and S. Seguí, Introduction to Data Science: A Python Approach to Concepts, Techniques and Applications, 1st ed. Cham, Switzerland: Springer, 2017.",
    "D. Martens, Data Science Ethics: Concepts, Techniques and Cautionary Tales, 1st ed. Oxford, U.K.: Oxford University Press, 2022.",
    "J. VanderPlas, Python Data Science Handbook: Essential Tools for Working with Data. Sebastopol, CA, USA: O’Reilly Media, 2016.",
    "F. Pedregosa et al., “Scikit-learn: Machine learning in Python,” Journal of Machine Learning Research, vol. 12, pp. 2825–2830, 2011.",
    "W. McKinney, “Data structures for statistical computing in Python,” in Proc. 9th Python in Science Conf., 2010, pp. 56–61.",
    "G. Salton and C. Buckley, “Term-weighting approaches in automatic text retrieval,” Information Processing & Management, vol. 24, no. 5, pp. 513–523, 1988.",
    "B. Sarwar, G. Karypis, J. Konstan and J. Riedl, “Item-based collaborative filtering recommendation algorithms,” in Proc. 10th Int. Conf. World Wide Web, 2001, pp. 285–295.",
    "Y. Koren, R. Bell and C. Volinsky, “Matrix factorization techniques for recommender systems,” Computer, vol. 42, no. 8, pp. 30–37, 2009.",
    "R. Burke, “Hybrid recommender systems: Survey and experiments,” User Modeling and User-Adapted Interaction, vol. 12, no. 4, pp. 331–370, 2002.",
    "J. Bobadilla, F. Ortega, A. Hernando and A. Gutiérrez, “Recommender systems survey,” Knowledge-Based Systems, vol. 46, pp. 109–132, 2013.",
    "G. Adomavicius and A. Tuzhilin, “Context-aware recommender systems,” in Recommender Systems Handbook, F. Ricci, L. Rokach, B. Shapira and P. B. Kantor, Eds. Boston, MA, USA: Springer, 2011, pp. 217–253.",
    "J. Carbonell and J. Goldstein, “The use of MMR, diversity-based reranking for reordering documents and producing summaries,” in Proc. 21st ACM SIGIR Conf., 1998, pp. 335–336.",
    "K. Järvelin and J. Kekäläinen, “Cumulated gain-based evaluation of IR techniques,” ACM Trans. Information Systems, vol. 20, no. 4, pp. 422–446, 2002.",
    "P. J. Rousseeuw, “Silhouettes: A graphical aid to the interpretation and validation of cluster analysis,” Journal of Computational and Applied Mathematics, vol. 20, pp. 53–65, 1987.",
    "J. H. Ward, “Hierarchical grouping to optimize an objective function,” Journal of the American Statistical Association, vol. 58, no. 301, pp. 236–244, 1963.",
    "L. Sweeney, “k-anonymity: A model for protecting privacy,” Int. J. Uncertainty, Fuzziness and Knowledge-Based Systems, vol. 10, no. 5, pp. 557–570, 2002.",
    "M. Feldman, S. A. Friedler, J. Moeller, C. Scheidegger and S. Venkatasubramanian, “Certifying and removing disparate impact,” in Proc. 21st ACM SIGKDD Conf., 2015, pp. 259–268.",
    "Internet Archive, “Open Library developer APIs.” [Online]. Available: https://openlibrary.org/developers/api (accessed Oct. 2026).",
]

# ============================================================================ ASSEMBLY
# body = cover/TOC (0-36) + ABSTRACT heading + new abstract + chapters + references + back matter (149-)
abstract_head, ref_head = E[37], E[142]
for el in E[38:149]:
    body.remove(el)
anchor = abstract_head
new = [para(P_BODY, a) for a in abstract] + [para(E[42], [(keywords[0], True), keywords[1]])] + OUTPUT
new += [copy.deepcopy(P_SECT), ref_head] + [para(P_REF, r) for r in REFS] + [copy.deepcopy(E[148])]
for el in new:
    anchor.addnext(el)
    anchor = el

# keyword paragraph keeps the template's bold-lead style but the second run must not be bold
kw = new[len(abstract)]
runs = kw.findall(qn("w:r"))
for b in runs[1].iter(qn("w:b")):
    b.getparent().remove(b)

# ---------------------------------------------------------------- cover page and tables
def set_text(p, value):
    pr = Paragraph(p, d._body)
    runs = [r for r in pr.runs if r.text.strip()]
    if runs:
        runs[0].text = value
        for r in runs[1:]:
            r.text = ""


for el in body.iterchildren():
    if el.tag != qn("w:p"):
        continue
    t = "".join(x.text or "" for x in el.iter(qn("w:t"))).strip()
    if t == "AutoML":
        set_text(el, "ATHENAEUM")
        sub = copy.deepcopy(el)
        set_text(sub, "Smart Library Gate Analytics and Gate-Context-Aware Book Recommendation")
        for sz in sub.iter(qn("w:sz")):
            sz.set(qn("w:val"), "30")
        el.addnext(sub)
        break

REG = "[REGISTER NUMBER]"
cover, team, evaluation = d.tables[0], d.tables[1], d.tables[-2]
cover.rows[0].cells[2].paragraphs[0].runs[0].text = "SANDEEP M K"
for r in cover.rows[0].cells[2].paragraphs[0].runs[1:]:
    r.text = ""
for i, val in ((1, REG),):
    ps = cover.rows[i].cells[2].paragraphs[0]
    ps.runs[0].text = val
    for r in ps.runs[1:]:
        r.text = ""
team_vals = [["1", "SANDEEP M K", REG], ["2", "[TEAMMATE NAME]", "[REGISTER NUMBER]"],
             ["3", "[TEAMMATE NAME]", "[REGISTER NUMBER]"]]
for row, vals in zip(team.rows[1:], team_vals):
    for cell, v in zip(row.cells, vals):
        rs = cell.paragraphs[0].runs
        rs[0].text = v
        for r in rs[1:]:
            r.text = ""
for i, v in ((0, REG), (1, "SANDEEP M K"), (2, "Athenaeum: Smart Library Analytics and Book Recommendation")):
    rs = evaluation.rows[i].cells[2].paragraphs[0].runs
    rs[0].text = v
    for r in rs[1:]:
        r.text = ""

# ---------------------------------------------------------------- back matter: replace the friend's images
def replace_images_with_note(heading_text, note):
    started = False
    for el in list(body.iterchildren()):
        if el.tag != qn("w:p"):
            continue
        t = "".join(x.text or "" for x in el.iter(qn("w:t"))).strip()
        if t == heading_text:
            started = True
            continue
        if started and t in ("MICROSOFT CERTIFICATE", "EVALUATION SHEET"):
            break
        if started and el.find(".//" + qn("w:drawing")) is not None:
            for r in el.findall(qn("w:r")):
                if r.find(".//" + qn("w:drawing")) is not None:
                    el.remove(r)
            if note:
                p = para(P_BODY, note)
                Paragraph(p, d._body).alignment = WD_ALIGN_PARAGRAPH.CENTER
                el.addnext(p)
                note = None


def back_matter_images(heading_text, images, width_cm, per_page):
    """Remove the template's images under a heading and insert ours, `per_page` per page."""
    started, anchor, removed = False, None, []
    for el in list(body.iterchildren()):
        if el.tag != qn("w:p"):
            continue
        t = "".join(x.text or "" for x in el.iter(qn("w:t"))).strip()
        if t == heading_text:
            started, anchor = True, el
            continue
        if started and t in ("MICROSOFT CERTIFICATE", "EVALUATION SHEET"):
            break
        if started and el.find(".//" + qn("w:drawing")) is not None:
            for r in el.findall(qn("w:r")):
                if r.find(".//" + qn("w:drawing")) is not None:
                    el.remove(r)
    for k, img in enumerate(images):
        p = para(P_BODY, "")
        po = Paragraph(p, d._body)
        po.alignment = WD_ALIGN_PARAGRAPH.CENTER
        po.paragraph_format.space_before = docx.shared.Pt(6)
        po.runs[0].add_picture(img, width=Cm(width_cm))
        if k and k % per_page == 0:
            br = docx.oxml.OxmlElement("w:r"); b_ = docx.oxml.OxmlElement("w:br"); b_.set(qn("w:type"), "page")
            br.append(b_); p.insert(1, br)
        anchor.addnext(p)
        anchor = p


SLIDES = os.path.join(FIG, "slides")
slide_files = sorted(os.path.join(SLIDES, f) for f in os.listdir(SLIDES) if f.endswith(".png")) if os.path.isdir(SLIDES) else []
back_matter_images("PPT HANDOUTS", slide_files, 13.2, 3)


def drop_extra_section_breaks(start_heading, end_heading):
    """Keep only the last section break between two headings (the template's handout
    pages had one per page; with more slides they would leave blank pages)."""
    inside, breaks = False, []
    for el in body.iterchildren():
        if el.tag != qn("w:p"):
            continue
        t = "".join(x.text or "" for x in el.iter(qn("w:t"))).strip()
        if t == start_heading:
            inside = True
        elif t == end_heading:
            break
        elif inside and el.find(".//" + qn("w:sectPr")) is not None:
            breaks.append(el)
    for el in breaks[:-1]:
        body.remove(el)
    # blank spacer paragraphs between the slides and the remaining break
    if breaks:
        prev = breaks[-1].getprevious()
        while prev is not None and prev.tag == qn("w:p") and prev.find(".//" + qn("w:drawing")) is None                 and not "".join(x.text or "" for x in prev.iter(qn("w:t"))).strip():
            nxt = prev.getprevious()
            body.remove(prev)
            prev = nxt


drop_extra_section_breaks("PPT HANDOUTS", "MICROSOFT CERTIFICATE")
cert = os.path.join(FIG, "certificate.png")
if os.path.exists(cert):
    back_matter_images("MICROSOFT CERTIFICATE", [cert], 16.0, 1)

# empty spacer paragraphs left behind on the back-matter pages would push content onto extra pages
for el in list(body.iterchildren()):
    if el.tag == qn("w:p") and el.find(".//" + qn("w:drawing")) is None and el.find(".//" + qn("w:sectPr")) is None:
        if not "".join(x.text or "" for x in el.iter(qn("w:t"))).strip() and el.getprevious() is not None:
            prev_t = "".join(x.text or "" for x in el.getprevious().iter(qn("w:t"))).strip()
            if prev_t in ("PPT HANDOUTS", "MICROSOFT CERTIFICATE"):
                body.remove(el)

# ---------------------------------------------------------------- table of contents (static, like the template)
sdt = next(el for el in body.iterchildren() if el.tag == qn("w:sdt"))
toc_ps = sdt.findall(".//" + qn("w:p"))
TOC1, TOC2 = toc_ps[1], toc_ps[2]
holder = toc_ps[0].getparent()
for p in toc_ps:
    holder.remove(p)


def toc_line(proto, label, page, num_id=None, first=False):
    p = copy.deepcopy(proto)
    for h in p.findall(qn("w:hyperlink")):
        p.remove(h)
    _clear_runs(p)
    if num_id is not None:
        p.find(qn("w:pPr")).find(qn("w:numPr")).find(qn("w:numId")).set(qn("w:val"), str(num_id))
    if first:
        p.find(qn("w:pPr")).find(qn("w:spacing")).set(qn("w:before"), "279")
    p.append(_run_like(proto, label))
    tab = docx.oxml.OxmlElement("w:r"); tab.append(docx.oxml.OxmlElement("w:tab")); p.append(tab)
    p.append(_run_like(proto, str(PAGES.get(label, ""))))
    holder.append(p)


toc_line(TOC1, "Abstract", None, first=True)
for n, title, subs in TOC_STRUCTURE:
    toc_line(TOC1, f"Chapter {n}: {title}", None)
    for sub in subs:
        toc_line(TOC2, sub, None, num_id=n)
for label in ("References", "PPT Handouts", "Microsoft Certificate", "Evaluation Sheet"):
    toc_line(TOC1, label, None)

# ask Word to refresh the table of contents and page numbers when the file is opened
settings = d.settings.element
if settings.find(qn("w:updateFields")) is None:
    uf = docx.oxml.OxmlElement("w:updateFields")
    uf.set(qn("w:val"), "true")
    settings.append(uf)

d.core_properties.author = "Sandeep M K"
d.core_properties.title = "Athenaeum - Project Report"
d.save(OUT)
print("saved", OUT)
