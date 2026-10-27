"""Builds docs/Athenaeum_Study_Guide.docx: a plain-language guide to the whole project.

Run: python docs/build_study_guide.py
"""
import json
import os

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

HERE = os.path.dirname(os.path.abspath(__file__))
FIG = os.path.join(HERE, "figures")
R = json.load(open(os.path.join(FIG, "results.json")))
OUT = os.path.join(HERE, "Athenaeum_Study_Guide.docx")
GREEN = RGBColor(0x12, 0x3B, 0x33)
BRASS = RGBColor(0x8A, 0x5F, 0x1C)

doc = Document()
sec = doc.sections[0]
sec.page_width, sec.page_height = Cm(21), Cm(29.7)
for side in ("left_margin", "right_margin"):
    setattr(sec, side, Cm(2.2))
sec.top_margin = sec.bottom_margin = Cm(2)

st = doc.styles
st["Normal"].font.name = "Calibri"
st["Normal"].font.size = Pt(11)
st["Normal"].paragraph_format.space_after = Pt(6)
st["Normal"].paragraph_format.line_spacing = 1.15
for name, size in (("Title", 30), ("Heading 1", 18), ("Heading 2", 14), ("Heading 3", 12)):
    s = st[name]
    s.font.name = "Cambria"
    s.font.size = Pt(size)
    s.font.color.rgb = GREEN
    s.font.bold = True
    rpr = s.element.get_or_add_rPr()
    fonts = rpr.find(qn("w:rFonts"))
    if fonts is None:
        fonts = OxmlElement("w:rFonts"); rpr.append(fonts)
    for a in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        fonts.set(qn(a), "Cambria")
    for t in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
        fonts.attrib.pop(qn(t), None)

# footer page numbers
fp = sec.footer.paragraphs[0]
fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = fp.add_run("Athenaeum study guide  ·  page ")
run.font.size = Pt(9)
for kind, text in (("begin", None), (None, "PAGE"), ("end", None)):
    r = fp.add_run(); r.font.size = Pt(9)
    if kind:
        el = OxmlElement("w:fldChar"); el.set(qn("w:fldCharType"), kind); r._r.append(el)
    else:
        el = OxmlElement("w:instrText"); el.set(qn("xml:space"), "preserve"); el.text = text; r._r.append(el)


def H(text, level=1):
    doc.add_heading(text, level)


def P(*parts, style=None):
    p = doc.add_paragraph(style=style)
    for part in parts:
        if isinstance(part, tuple):
            r = p.add_run(part[0]); r.bold = True
        else:
            p.add_run(part)
    return p


def B(items, numbered=False, plain=False):
    for n, it in enumerate(items, 1):
        if numbered or plain:
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Cm(0.9)
            p.paragraph_format.first_line_indent = Cm(-0.6)
            p.paragraph_format.space_after = Pt(3)
            if numbered:
                p.add_run(f"{n}.  ").bold = True
        else:
            p = doc.add_paragraph(style="List Bullet")
        if isinstance(it, tuple):
            p.add_run(it[0]).bold = True
            p.add_run(" " + it[1])
        else:
            p.add_run(it)


def shade(cell, hex_):
    tcpr = cell._tc.get_or_add_tcPr()
    sh = OxmlElement("w:shd"); sh.set(qn("w:val"), "clear"); sh.set(qn("w:color"), "auto"); sh.set(qn("w:fill"), hex_)
    tcpr.append(sh)


def TABLE(header, rows, widths):
    t = doc.add_table(rows=1, cols=len(header))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, h in enumerate(header):
        c = t.rows[0].cells[i]
        c.text = ""
        r = c.paragraphs[0].add_run(h); r.bold = True; r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        shade(c, "123B33")
    for row in rows:
        cells = t.add_row().cells
        for i, v in enumerate(row):
            cells[i].text = str(v)
    for row in t.rows:
        for i, w in enumerate(widths):
            row.cells[i].width = Cm(w)
            for p in row.cells[i].paragraphs:
                p.paragraph_format.space_after = Pt(2)
                for r in p.runs:
                    r.font.size = Pt(10)
    doc.add_paragraph()


def TIP(text):
    t = doc.add_table(rows=1, cols=1)
    c = t.rows[0].cells[0]
    shade(c, "F1E3C6")
    c.text = ""
    r = c.paragraphs[0].add_run("Say this: "); r.bold = True; r.font.color.rgb = BRASS
    c.paragraphs[0].add_run(text)
    doc.add_paragraph()


def IMG(name, width=16):
    path = os.path.join(FIG, name)
    if os.path.exists(path):
        doc.add_picture(path, width=Cm(width))
        doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER


m = R["rec"]
gain = round((m["context"]["ndcg"] / m["hybrid"]["ndcg"] - 1) * 100)

# =============================================================== cover
doc.add_paragraph()
doc.add_paragraph("Athenaeum", style="Title")
P("Study guide: everything you need to understand, run and present the project")
P(("Course: "), "Data Science Ecosystem (23CS2024)  ·  ", ("Student: "), "Sandeep M K")
P("Read this from start to end once. Sections 1–3 tell you what the project is and how to run it. "
  "Section 4 walks through every screen of the app. Section 5 explains every concept in simple words. "
  "Sections 6–8 prepare you for the presentation and the viva.")
H("Contents", 2)
B(["1. The project in five minutes", "2. How to run the project (step by step)", "3. Where the data comes from",
   "4. Every tab of the app explained", "5. Concepts explained simply (the subject)", "6. What is new in our project",
   "7. How the project matches the syllabus and the rubric", "8. Presenting the 9 slides",
   "9. Viva questions and answers", "10. Honest limitations", "11. Which file does what"], plain=True)
doc.add_page_break()

# =============================================================== 1
H("1. The project in five minutes")
P("A college library collects data every day: who enters, when they leave, which books they borrow and how "
  "they rate them. Usually nobody analyses this. ", ("Athenaeum"), " is a web application that collects this "
  "data and uses data science to make decisions from it.")
P("It does three jobs:")
B([("Gate log:", "every student scans their ID when they enter and again when they leave. The app always knows who is inside and how long people stay."),
   ("Insights:", "it analyses the data: averages, patterns, statistical tests, predictions (how busy will it be? will this book come back late?) and groups of similar readers."),
   ("Book recommendations:", "it suggests the next book for each student and explains why.")])
P(("Our special idea (the “novel” part): "), "the recommender also looks at how long each student usually stays "
  "in the library. People who stay long tend to pick long books; people who drop in for 20 minutes prefer short "
  f"ones. Using this improved the recommendation score by about {gain}% compared with the normal method.")
P(("Second new idea: "), "the app predicts how full the reading room will be each hour and warns staff before it fills up.")
P(("Ethics: "), "student IDs are hidden (anonymised), we check that the models treat everyone fairly, and every "
  "recommendation shows its reasons.")
TIP("Athenaeum turns everyday library records into decisions: it logs the gate, analyses usage, predicts crowding "
    "and late returns, and recommends books using a new method that also considers how long each student stays.")

# =============================================================== 2
H("2. How to run the project (step by step)")
H("2.1 One-time setup", 2)
B(["Install Python 3.10 or newer (python.org). During setup tick “Add Python to PATH”.",
   "Open the project folder: D:\\library_managment system",
   "Click the address bar of File Explorer, type cmd and press Enter. A black command window opens in that folder.",
   "Install the libraries once:  pip install -r requirements.txt"], numbered=True)
H("2.2 Every time you want to show the project", 2)
B(["In the command window type:  python run.py   and press Enter.",
   "Wait until you see “Running on http://127.0.0.1:5000”.",
   "Open Chrome or Edge and go to  http://127.0.0.1:5000",
   "Wait about 30 seconds the first time: the models train in the background. After that every page is instant.",
   "To stop the app, click the command window and press Ctrl + C."], numbered=True)
TABLE(["Problem", "Fix"], [
    ["“python is not recognised”", "Reinstall Python and tick “Add Python to PATH”, then open a new command window."],
    ["“No module named flask”", "Run  pip install -r requirements.txt  again."],
    ["Charts are empty", "The charts load from the internet (Chart.js, d3). Connect to Wi-Fi or a phone hotspot."],
    ["“Address already in use”", "The app is already running in another window. Use that one, or close it first."],
    ["A page shows loading for long", "The first load trains the models; wait 30 seconds and refresh."],
    ["Want fresh data", "python -m app.seed   (re-creates all members, visits and loans)"],
    ["Want to re-download the books", "python -m app.scraper   (needs internet, takes ~3 minutes)"],
    ["Check everything works", "pip install pytest   then   python -m pytest -q   (36 tests should pass)"],
], [5.5, 11])
H("2.3 A 5-minute demo you can follow", 2)
B([("Gate:", "type KU24000 and press Enter (checked in). Type it again (checked out, shows minutes stayed). Press “Send 8 readers through the gate”."),
   ("Today:", "show the live numbers, who is inside, and the “Expected crowd today” chart with the warnings."),
   ("Discover:", "pick a random reader. Show the “Fits your visits” method and its reasons. Switch to “Best blend” to compare. Scroll to the scorecard."),
   ("Insights:", "show the heatmap, one hypothesis card, the forecast, the late-return risk checker, and the personas."),
   ("Reading web:", "drag the network graph."),
   ("Privacy & fairness:", "show the anonymised table and the fairness numbers.")], numbered=True)
doc.add_page_break()

# =============================================================== 3
H("3. Where the data comes from")
H("3.1 Books: web-scraped (real data)", 2)
P("Web scraping means a program visits a website and copies information automatically. Our program "
  "(app/scraper.py) asks Open Library, a free online library catalogue, for the most-read books in 18 genres. "
  "For every book it collects the title, author, year, number of pages, the average rating given by Open Library "
  "users, how many people want to read it, and the book’s description.")
TABLE(["Step", "What happened"], [
    ["Collected", "1,980 book records from 18 genres"],
    ["Removed duplicates", "the same book often appears under two genres"],
    ["Kept English editions only", "removed translations like a German edition of a book"],
    ["Fixed wrong genres", "e.g. a novel tagged “computers” was not allowed into Computer Science"],
    ["Removed books with no description", "a recommender needs text to compare books"],
    ["Result", "510 clean, real books"],
], [5.5, 11])
P("This is called ", ("data cleaning"), ". Real data is always messy; cleaning it is a big part of data science.")
H("3.2 Students, visits, loans and ratings: simulated", 2)
P("We cannot use real students’ data (privacy). So app/seed.py creates 600 imaginary students. Each one gets "
  "hidden habits: which genres they like (depends on their department), how often they visit, how long they "
  "usually stay, how careful they are with due dates. Every visit, loan and rating is then produced from these "
  f"habits. Result: {R['counts']['visits']:,} visits, {R['counts']['loans']:,} loans and {R['counts']['ratings']:,} ratings over 120 days.")
P("We added realism on purpose: exam weeks are busier, weekends are quieter, first-year students are a bit "
  "more careless with returns, and about 7% of visit purposes are left empty, so we must handle missing data.")
TIP("The books are real and web-scraped from Open Library. Student activity is simulated from realistic habits "
    "because real student records are private; the same code works unchanged on real gate data.")
doc.add_page_break()

# =============================================================== 4
H("4. Every tab of the app explained")
P("The left menu has eight pages. For each: what you see, the concept behind it, and what to say.")

H("4.1 Today", 2)
IMG("today_crop.png", 15)
B([("Top numbers:", "readers inside now, visits today, average stay, books on loan, overdue books."),
   ("Arrivals by hour:", "bar chart of how many people came in each hour today."),
   ("In the building now:", "list of everyone currently inside and for how long."),
   ("Expected crowd today:", "our occupancy forecast. The line is how many people we expect inside each hour; the dotted line is the 60 seats. Red warnings appear when it will be over 70% or 90% full."),
   ("Gate activity:", "the latest check-ins and check-outs. The page refreshes every 10 seconds.")])
P(("Concept: "), "this is a live dashboard. The forecast combines a regression prediction of arrivals with how long people usually stay.")

H("4.2 Gate", 2)
IMG("gate.png", 15)
P("A kiosk screen. Type or scan a member ID. First scan = check in, second scan = check out (it shows the minutes "
  "stayed on a “rubber stamp”). The circle shows how full the room is. “Send 8 readers through the gate” "
  "simulates traffic for a demo.")
P(("Concept: "), "real-time data acquisition. Every scan is stored instantly in the database and all other pages update.")

H("4.3 Discover (the recommender)", 2)
IMG("discover.png", 15)
P("Pick a reader. You get 10 suggested books, each with reasons such as “Because you read To Kill a Mockingbird”, "
  "“278 pages suits your ~65-min visits” or “5 readers like you loved it”. The buttons switch between seven methods:")
TABLE(["Button", "Method", "Idea in one line"], [
    ["Fits your visits", "Gate-context hybrid (ours)", "Best blend, then prefers books whose length suits how long this reader stays"],
    ["Best blend", "Hybrid", "Mixes all the methods below, then spreads picks across topics"],
    ["Similar books", "Content-based filtering", "Books whose description and genre resemble what you liked"],
    ["Readers like them", "User-based collaborative filtering", "Find students with similar taste, suggest what they liked"],
    ["Often read together", "Item-based collaborative filtering", "Books borrowed by the same people as your books"],
    ["Hidden tastes", "Matrix factorisation (SVD)", "Learns hidden taste factors from the whole ratings table"],
    ["Library favourites", "Popularity", "Highest rated and most borrowed; used for new students"],
], [3.5, 5, 8])
P("The ", ("scorecard"), " at the bottom tests every method fairly: we hide some books each student really "
  "borrowed and check whether each method finds them. Our method scores best.")

H("4.4 Catalogue", 2)
P("All 510 scraped books with search and genre filter. Click a book to see details, issue it to a student, and "
  "see “Readers also liked” (similar books with reasons).")

H("4.5 Members", 2)
P("All 600 students. Click one to see their visits, loans (with a “Mark returned” button), reading taste and personal suggestions.")

H("4.6 Insights (five sub-tabs)", 2)
H("Usage patterns", 3)
IMG("eda_crop.png", 14)
P("Exploratory data analysis (EDA): a heatmap of arrivals by weekday and hour (darker = busier), daily visits, "
  "a histogram of stay lengths, why people came (donut), department table, most borrowed books, genre "
  "popularity, a correlation table, summary statistics (mean, median, variance, standard deviation…) and a "
  "missing-values table.")
H("Questions & evidence", 3)
P("Eight hypothesis tests. Each card asks a real question, states H₀ (nothing interesting is happening) and H₁, "
  "runs the right statistical test, shows the p-value and says “Reject H₀” or “Fail to reject H₀”, with a plain "
  "sentence. Below: 95% confidence intervals.")
TABLE(["Question", "Test", "Result"], [[q.rstrip("?"), t.replace(" test of independence", ""),
                                        "Real effect" if d.startswith("Reject") else "No proof of an effect"]
                                       for q, t, _, _, d, _ in R["tests"]], [8.5, 4, 4])
H("Footfall forecast", 3)
P("Predicts visitors per hour with three regression models and compares them with R², MAE and RMSE. Multiple "
  f"regression wins (R² = {R['forecast'][2][1]:.2f}, i.e. it explains {round(R['forecast'][2][1]*100)}% of the ups and downs).")
H("Late returns", 3)
P("Predicts whether a book will come back late using logistic regression, KNN, decision tree and random forest. "
  "Shows accuracy, precision, recall, F1, ROC curves, confusion matrices, which factors matter most, and the "
  "decision tree written as rules. The “Check a loan before issuing it” box gives a live risk % with reasons.")
H("Reader personas", 3)
IMG("personas_crop.png", 14)
P("K-means clustering puts students into groups with similar behaviour, without being told the groups. "
  "Names are generated automatically, e.g. “Heavy borrowers & Genre explorers”. The scatter plot uses PCA to "
  "draw 8 features on a flat map. The elbow/silhouette chart shows how the number of groups was chosen. "
  "Hierarchical (agglomerative) clustering is a second opinion.")

H("4.7 Reading web", 2)
IMG("network.png", 14)
P("A network graph. Each circle is a book; a line joins two books borrowed by the same students (thicker = more "
  "shared readers). You can drag and zoom. “Copy as Neo4j Cypher” exports it to Neo4j, a graph database (a lab exercise).")

H("4.8 Privacy & fairness", 2)
IMG("trust_crop.png", 14)
B([("Anonymised export:", "names removed, IDs replaced by secret codes (hashing), times rounded to the hour."),
   ("k-anonymity:", f"every combination of department + year + gender must match at least 5 people so nobody can be identified. Raw data: k = {R['ethics']['k_raw']}; after grouping years and departments: k = {R['ethics']['k_after']}."),
   ("Fairness:", f"gender is never used by the models, but we still check results per gender. Disparate impact = {R['ethics']['di']:.2f}; above 0.8 means fair."),
   ("Consent:", f"{R['ethics']['opted_out']} students opted out of personal suggestions; they only get popular books.")])
doc.add_page_break()

# =============================================================== 5
H("5. Concepts explained simply")
H("5.1 Describing data (descriptive statistics)", 2)
TABLE(["Term", "Meaning", "In our project"], [
    ["Mean", "the average: add everything, divide by how many", f"average stay {R['describe']['duration_min']['mean']:.1f} min"],
    ["Median", "the middle value when sorted; not fooled by extremes", f"{R['describe']['duration_min']['median']:.1f} min"],
    ["Variance", "how spread out the values are (in squared units)", f"{R['describe']['duration_min']['var']:.0f}"],
    ["Standard deviation", "square root of variance; typical distance from the mean", f"{R['describe']['duration_min']['std']:.1f} min"],
    ["Skewness", "is the data lopsided? positive = long tail to the right", f"{R['describe']['duration_min']['skew']:.2f}: a few very long visits"],
    ["Outlier (IQR rule)", "a value far outside the middle 50% of data", "very long or very short visits"],
    ["Missing values", "empty cells in the data", "7% of visit purposes; shown as “Not recorded”"],
    ["Correlation (r)", "do two things rise together? −1 to +1", "visits and loans: r ≈ 0.37"],
], [3.5, 7.5, 5.5])
H("5.2 Hypothesis testing (proving things with statistics)", 2)
P("We want to know if a difference is real or just luck. We assume ", ("H₀"), " (null hypothesis: no difference) "
  "and see how surprising our data would be if H₀ were true. That surprise is the ", ("p-value"), ". If p < 0.05 "
  "(less than 5% chance of seeing this by luck) we ", ("reject H₀"), ": the effect is real. Otherwise we ",
  ("fail to reject H₀"), ": there isn’t enough evidence.")
TABLE(["Test", "Used when"], [
    ["Welch t-test", "compare the averages of two groups (weekday vs weekend stay)"],
    ["One-way ANOVA", "compare the averages of 3+ groups (stay across departments)"],
    ["Chi-square test", "are two categories linked? (department vs visit purpose)"],
    ["Pearson / Spearman correlation", "do two numbers move together? (visits vs loans)"],
    ["Mann-Whitney U", "compare two groups when data is not bell-shaped (first-years’ late days)"],
    ["Two-proportion z-test", "compare two percentages (late rate of men vs women)"],
    ["Shapiro-Wilk", "is the data bell-shaped (normal)? (stay times are not)"],
    ["Confidence interval", "a range that contains the true value with 95% confidence"],
    ["Effect size", "how big the difference is, not just whether it exists"],
], [5, 11.5])
H("5.3 Machine learning", 2)
P(("Supervised learning"), " learns from examples with known answers (past visits → predict visits). ",
  ("Unsupervised learning"), " finds structure without answers (grouping readers).")
TABLE(["Model", "Simple idea", "Used for"], [
    ["Linear regression", "fits a straight line through the data", "footfall trend"],
    ["Polynomial regression", "fits a curve (hour of day has a morning and afternoon peak)", "footfall by hour"],
    ["Multiple regression", "uses several inputs at once (hour, weekday, weekend, yesterday’s count)", "best footfall model"],
    ["Logistic regression", "gives a probability (0–100%) of yes/no", "late-return risk"],
    ["KNN", "look at the K most similar past cases and copy their answer", "late returns"],
    ["Decision tree", "a flowchart of yes/no questions", "late returns, readable rules"],
    ["Random forest", "many decision trees voting together", "late returns"],
    ["K-means", "puts points into K groups around centre points", "reader personas"],
    ["Agglomerative clustering", "joins the closest pairs step by step into a tree (dendrogram)", "second opinion"],
    ["PCA", "squashes many features into 2 so we can draw them", "personas map"],
], [3.8, 8, 4.7])
H("5.4 Checking how good a model is", 2)
TABLE(["Measure", "Meaning"], [
    ["Train / test split", "learn on old data, test on data the model never saw"],
    ["Cross-validation", "repeat training/testing 5 times on different parts; average the scores"],
    ["R²", "share of variation explained by a regression (1 = perfect, 0 = useless)"],
    ["MAE / RMSE", "typical prediction error (RMSE punishes big mistakes more)"],
    ["Accuracy", "share of all predictions that were right"],
    ["Precision", "of the loans we flagged as late, how many really were late"],
    ["Recall", "of the loans that really were late, how many we caught"],
    ["F1", "a single score balancing precision and recall"],
    ["Confusion matrix", "a 2×2 table of right and wrong predictions"],
    ["ROC-AUC", "how well the model ranks risky above safe loans (0.5 = guessing, 1 = perfect)"],
    ["Class imbalance", "only 33% of loans are late, so we gave late loans more weight (class weights)"],
    ["Silhouette score", "how well separated clusters are"],
    ["Elbow method", "choose K where adding more groups stops helping much"],
    ["Adjusted Rand index", "how much two clusterings agree"],
], [4, 12.5])
H("5.5 Recommender systems", 2)
TABLE(["Term", "Meaning"], [
    ["Content-based filtering", "recommend items similar in content to what the user liked"],
    ["TF-IDF", "turns text into numbers; rare, meaningful words get more weight than common words"],
    ["Cosine similarity", "measures how similar two items or users are (1 = identical direction)"],
    ["Collaborative filtering", "uses other people’s behaviour: similar users, or items liked by the same people"],
    ["Matrix factorisation (SVD)", "learns hidden “taste factors” for users and books from the ratings table"],
    ["Hybrid recommender", "combines several methods to cover each one’s weaknesses"],
    ["Cold start", "a new user with no history; we fall back to department favourites and popularity"],
    ["Implicit vs explicit feedback", "a loan (implicit: they borrowed it) vs a star rating (explicit)"],
    ["MMR (diversity)", "re-orders the list so it is not ten copies of the same topic"],
    ["Hold-out evaluation", "hide 20% of each student’s books, retrain, see if the method finds them"],
    ["NDCG@10", "ranking quality of the top 10: finding the right book near the top scores more"],
    ["Recall@10 / Hit rate", "share of hidden books found / share of students with at least one hit"],
    ["Coverage", "share of the whole catalogue that ever gets recommended"],
], [5, 11.5])
H("5.6 Ethics in data science", 2)
TABLE(["Term", "Meaning"], [
    ["Privacy & consent", "collect only what is needed; respect a student’s choice to opt out"],
    ["Pseudonymisation", "replace IDs with secret codes (salted SHA-256 hash) that cannot be reversed"],
    ["k-anonymity", "every record looks the same as at least k−1 others, so no one can be singled out"],
    ["Generalisation / suppression", "make details coarser (year → Junior/Senior) or hide them"],
    ["Bias & fairness", "a model should not treat groups (e.g. men vs women) unfairly"],
    ["Disparate impact", "ratio of good-outcome rates between groups; ≥ 0.8 passes the four-fifths rule"],
    ["Transparency / explainability", "show why a decision was made (reasons, top factors, tree rules)"],
], [5, 11.5])
H("5.7 Software words", 2)
TABLE(["Term", "Meaning"], [
    ["Python", "the programming language used for all the data science"],
    ["pandas / NumPy", "Python libraries for tables of data and fast maths"],
    ["SciPy", "statistics library (the hypothesis tests)"],
    ["scikit-learn", "machine-learning library (models, TF-IDF, clustering)"],
    ["SQLite", "a small database stored in one file (data/library.db)"],
    ["Flask / REST API", "the Python web server; the web pages ask it for data at addresses like /api/overview"],
    ["Chart.js / d3.js", "JavaScript libraries that draw the charts and the network in the browser"],
    ["API (Open Library)", "a website address that returns data for programs instead of pages for people"],
    ["Neo4j / Cypher", "a graph database and its query language"],
    ["pytest", "automatic tests that check the code still works (36 tests)"],
    ["Git / GitHub", "version control; the code is saved online at github.com/sandeepmk2006"],
], [4, 12.5])
doc.add_page_break()

# =============================================================== 6
H("6. What is new in our project")
H("6.1 Gate-context-aware hybrid recommender", 2)
IMG("context_fit.png", 12)
P("Each dot is a student. Students who stay longer per visit (right) borrow longer books (up). The line is a "
  f"regression: pages grow with stay time (correlation r = {R['ctx'][1]:.2f}).")
B(["Step 1: compute the normal hybrid score for every book.",
   "Step 2: from the gate log, predict the ideal book length for this student from their usual stay time.",
   "Step 3: give each book a “length fit” score (1 = perfect length) and multiply: Score = Hybrid × (0.7 + 0.3 × fit).",
   "Step 4: re-order with MMR for variety."], numbered=True)
P(f"Result: NDCG@10 went from {m['hybrid']['ndcg']:.3f} (plain hybrid) to {m['context']['ndcg']:.3f} (ours), about {gain}% better. "
  "The 0.3 weight was chosen on separate data (a validation split) so the test is fair. It also works for "
  "students who have visited but never borrowed.")
H("6.2 Occupancy forecast with alerts", 2)
P("Occupancy(hour) = people inside now × share still inside later + predicted arrivals × share still inside. "
  "The arrivals come from multiple regression; the “share still inside” comes from the measured stay times. "
  "If the forecast passes 70% of seats the app suggests a desk assistant; above 90% it suggests opening an overflow hall.")
TIP("Normal recommenders only look at what you borrowed. Ours also looks at how you use the library building. "
    "That is the novel part, and it improved ranking quality by about 17%.")

# =============================================================== 7
H("7. How the project matches the syllabus and the rubric")
TABLE(["Syllabus module", "Where it is in the project"], [
    ["1  Basics of data science", "real application; data types: tables, time series, text, graph; Python toolbox"],
    ["2  Understanding data", "import, filter, sort, group, rank, missing values, 10 kinds of charts (Usage patterns)"],
    ["3  Statistical inference", "mean/median/variance/std, correlation, 8 hypothesis tests, confidence intervals"],
    ["4  Machine learning", "linear/multiple/polynomial/logistic regression, KNN, decision tree, k-means, agglomerative, evaluation"],
    ["5  Recommender systems", "content-based, collaborative, hybrid, evaluation of recommenders"],
    ["6  Ethics", "privacy, consent, anonymisation, k-anonymity, fairness, explainability"],
    ["Lab", "pandas/NumPy, EDA, inference, Neo4j export, visualisation, dashboards, regression and classification analysis, NLP (TF-IDF), real-time gate data"],
], [4.5, 12])
TABLE(["Rubric (20 marks)", "How we cover it"], [
    ["Problem & dataset (5)", "real-time problem (live gate), innovative objectives, web-scraped dataset from Open Library"],
    ["Methodology & results (10)", "novel gate-context method, fully implemented, results interpreted, compared against 6 other methods and several models"],
    ["Report (5)", "department format, 18 cited references, figures and tables; written in our own words"],
], [4.5, 12])

# =============================================================== 8
H("8. Presenting the 9 slides")
TABLE(["#", "Slide", "What to say (about 1 minute each)"], [
    ["1", "Title", "Name, course, “Athenaeum: a smart library system with a live gate, analytics and a new recommender.”"],
    ["2", "Problem statement", "Four problems: paper registers, books never discovered, late returns noticed too late, recommenders that ignore how people use the library."],
    ["3", "Web-scraped dataset", "1,980 records scraped from Open Library, cleaned to 510; how cleaning worked; student activity simulated for privacy."],
    ["4", "Architecture", "Scraper and gate → SQLite database → Python engine → Flask web app."],
    ["5", "Proposed method", "Stay time predicts book length (the scatter plot); three steps of the method."],
    ["6", "Forecasting & late returns", f"Multiple regression explains {round(R['forecast'][2][1]*100)}% of footfall; four classifiers compared with F1 and ROC-AUC."],
    ["7", "Recommender evaluation", f"Fair hold-out test; ours is best; +{gain}% NDCG over the hybrid."],
    ["8", "Occupancy forecast", "Formula in words; the app warns staff before the room fills."],
    ["9", "Conclusion", "What we showed, next steps, thank you. Then do the live demo (section 2.3)."],
], [0.8, 3.7, 12])

# =============================================================== 9
H("9. Viva questions and answers")
QA = [
    ("What is your project?", "A smart library system that logs entries and exits, analyses usage with statistics and machine learning, and recommends books with a new method that also uses how long each student stays."),
    ("Where did you get the data?", "Books are web-scraped from the Open Library API: 1,980 records cleaned to 510. Student activity is simulated from realistic habits because real student data is private."),
    ("Why is the dataset web-scraped and not a Kaggle dataset?", "Scraping gives fresh, real data and shows the full pipeline: collection, cleaning and storage. The rubric also asks for a web-scraped dataset."),
    ("How did you clean the data?", "Removed duplicates, kept English editions only, removed novels wrongly tagged as non-fiction, dropped books without descriptions, filled missing page counts with the genre median."),
    ("What is new in your project?", "The gate-context-aware recommender: it uses each student’s typical stay time to prefer books of a suitable length. It improved NDCG by about 17%. Also the occupancy forecast with alerts."),
    ("What is a p-value?", "The chance of seeing data this extreme if there were really no effect. Below 0.05 we reject the null hypothesis."),
    ("Give one hypothesis you tested.", "H₀: first-year students return books as late as others. Mann-Whitney U test, p < 0.001, so we reject H₀: first-years return later."),
    ("Why median and mean differ for stay time?", "Stay times are right-skewed: a few very long visits pull the mean up, so the median is lower."),
    ("Difference between linear and logistic regression?", "Linear predicts a number (visitors per hour); logistic predicts a probability of a yes/no outcome (late or not)."),
    ("What is R²?", f"How much of the variation the model explains. Our best footfall model has R² = {R['forecast'][2][1]:.2f}."),
    ("Precision vs recall?", "Precision: of the loans we flagged as late, how many were late. Recall: of all late loans, how many we caught."),
    ("Why did you use class weights?", "Only a third of loans are late, so the model would ignore them. Class weights make the rare class count more and raised F1."),
    ("How did you choose K in k-means?", "With the elbow method and the silhouette score; we checked k from 2 to 8."),
    ("What is TF-IDF and cosine similarity?", "TF-IDF turns each book description into a vector of word importance; cosine similarity measures how alike two vectors are."),
    ("Content-based vs collaborative filtering?", "Content-based compares books’ text and genre; collaborative uses what similar students borrowed or rated."),
    ("What is the cold-start problem?", "A new student has no history. We use their department’s favourites and popular books, and the gate context if they have visited."),
    ("How did you evaluate the recommenders?", "Hid 20% of each student’s books, retrained, and checked if each method’s top 10 found them: precision, recall, NDCG, hit rate, coverage."),
    ("What is NDCG?", "A ranking score that rewards putting the right books near the top of the list."),
    ("How do you protect privacy?", "IDs are replaced by salted hashes, names removed, times rounded, k-anonymity checked, and students can opt out."),
    ("How do you check fairness?", f"Gender is not used as an input, and we compare outcomes per gender: disparate impact {R['ethics']['di']:.2f}, above the 0.8 rule."),
    ("What are the limitations?", "Student activity is simulated, including the stay-time/book-length link, so the gain should be confirmed on real library data."),
    ("What would you do next?", "Test on real gate data, connect an RFID reader, add time-of-day context, send alerts by e-mail."),
    ("Which tools did you use?", "Python, pandas, NumPy, SciPy, scikit-learn, SQLite, Flask, Chart.js, d3.js, pytest, Git."),
]
for q, a in QA:
    p = doc.add_paragraph()
    p.add_run("Q: " + q).bold = True
    doc.add_paragraph("A: " + a)

# =============================================================== 10
H("10. Honest limitations")
B(["Student visits, loans and ratings are simulated (books are real).",
   "The link between stay time and book length was part of the simulation, so the 17% gain must be re-checked on real data. Say this openly: examiners respect honesty.",
   "Absolute recommendation scores look small (NDCG 0.07) because each student reads only a few of 510 books; what matters is the comparison between methods.",
   "Charts need an internet connection to load their libraries."])

# =============================================================== 11
H("11. Which file does what")
TABLE(["File", "What it does"], [
    ["run.py", "starts the app"],
    ["app/scraper.py", "web scraper for Open Library + cleaning"],
    ["app/seed.py", "creates the simulated students, visits, loans, ratings"],
    ["app/db.py", "database tables and loading data into pandas"],
    ["app/analytics.py", "EDA, hypothesis tests, regression, occupancy forecast, classification, clustering"],
    ["app/recommender.py", "the seven recommenders and their evaluation"],
    ["app/ethics.py", "anonymisation, k-anonymity, fairness"],
    ["app/graph.py", "reading-web network and Neo4j export"],
    ["app/server.py", "the web server (API)"],
    ["app/static/", "the web pages (HTML, CSS, JavaScript)"],
    ["tests/", "36 automatic tests"],
    ["data/books_scraped.csv", "the scraped, cleaned book list"],
    ["docs/Athenaeum_Project_Report.docx", "the project report"],
    ["docs/Athenaeum_Presentation.pptx", "the 9-slide presentation"],
    ["docs/SYLLABUS_MAPPING.md", "detailed syllabus mapping"],
], [6, 10.5])

doc.core_properties.author = "Sandeep M K"
doc.core_properties.title = "Athenaeum study guide"
doc.save(OUT)
print("saved", OUT)
