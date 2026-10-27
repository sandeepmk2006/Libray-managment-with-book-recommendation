"""Generate the report's diagrams and result charts into docs/figures/.

Run from the project root:  python docs/make_figures.py
"""
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.db import connect, load_frames  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "figures")
GREEN, BRASS, INK, SOFT, PAPER, BLUE, RED = "#123b33", "#b9852f", "#17201d", "#55625d", "#eef1ec", "#2d5d8a", "#b4442c"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "axes.edgecolor": SOFT,
                     "axes.spines.top": False, "axes.spines.right": False})
res = json.load(open(os.path.join(OUT, "results.json")))


def box(ax, x, y, w, h, title, lines, dark=False):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08",
                                fc=GREEN if dark else "white", ec=GREEN, lw=1.6))
    c = "white" if dark else INK
    ax.text(x + w / 2, y + h - 0.28, title, ha="center", va="top", fontsize=12, weight="bold", color=c)
    ax.text(x + w / 2, y + h - 0.68, "\n".join(lines), ha="center", va="top", fontsize=9.5,
            color="#dfe9e3" if dark else SOFT, linespacing=1.5)


def arrow(ax, a, b, both=False):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle="<|-|>" if both else "-|>", mutation_scale=14,
                                 color=SOFT, lw=1.4))


# ---------------------------------------------------------------- architecture
fig, ax = plt.subplots(figsize=(11, 4.2))
ax.set_xlim(0, 11); ax.set_ylim(0, 4.2); ax.axis("off")
box(ax, 0.2, 2.25, 2.3, 1.7, "Open Library", ["web scraper", "search + work pages", "510 books"])
box(ax, 0.2, 0.25, 2.3, 1.7, "Library gate", ["ID scan in / out", "live entry & exit", "30,132 visits"])
box(ax, 3.2, 0.75, 2.1, 2.7, "SQLite", ["members · books", "visits · loans", "ratings"])
box(ax, 6.0, 0.25, 2.5, 3.7, "Python engine", ["pandas · NumPy", "SciPy statistics", "scikit-learn models",
                                               "7 recommenders", "occupancy forecast", "ethics audit"], dark=True)
box(ax, 9.1, 0.75, 1.75, 2.7, "Web app", ["Flask REST API", "JS modules", "Chart.js · d3"])
arrow(ax, (2.5, 3.1), (3.2, 2.6)); arrow(ax, (2.5, 1.1), (3.2, 1.6))
arrow(ax, (5.3, 2.1), (6.0, 2.1), both=True); arrow(ax, (8.5, 2.1), (9.1, 2.1), both=True)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "architecture.png"), dpi=170); plt.close(fig)

# ---------------------------------------------------------------- workflow (two rows of four)
steps = [("1. Scrape", "Open Library API\n1,980 candidates"), ("2. Clean", "dedupe, English only,\ngenre checks: 510 kept"),
         ("3. Collect", "gate scans, loans\nand ratings"), ("4. Explore", "EDA, missing data,\ncorrelation"),
         ("5. Infer", "8 hypothesis tests,\nconfidence intervals"), ("6. Model", "regression, classifiers,\nclustering"),
         ("7. Recommend", "7 methods incl. the\ngate-context hybrid"), ("8. Evaluate", "hold-out NDCG,\nfairness audit")]
fig, ax = plt.subplots(figsize=(11, 4.6))
ax.set_xlim(0, 11); ax.set_ylim(0, 4.6); ax.axis("off")
for i, (t, d) in enumerate(steps):
    row, col = divmod(i, 4)
    x, y = 0.2 + col * 2.75, 2.5 - row * 2.2
    dark = t.startswith("7")
    ax.add_patch(FancyBboxPatch((x, y), 2.2, 1.7, boxstyle="round,pad=0.02,rounding_size=0.1",
                                fc=BRASS if dark else "white", ec=GREEN, lw=1.4))
    ax.text(x + 1.1, y + 1.45, t, ha="center", va="top", weight="bold", fontsize=12, color=INK)
    ax.text(x + 1.1, y + 0.95, d, ha="center", va="top", fontsize=9.5, color=INK if dark else SOFT, linespacing=1.4)
    if col < 3:
        arrow(ax, (x + 2.22, y + 0.85), (x + 2.75, y + 0.85))
arrow(ax, (0.2 + 3 * 2.75 + 1.1, 2.5), (1.3, 1.98))
fig.tight_layout(); fig.savefig(os.path.join(OUT, "workflow.png"), dpi=170); plt.close(fig)

# ---------------------------------------------------------------- scraped catalogue
g = pd.Series(res["scrape"]["genres"]).sort_values()
fig, ax = plt.subplots(figsize=(8, 5))
ax.barh(g.index, g.values, color=GREEN)
for i, v in enumerate(g.values):
    ax.text(v + 0.3, i, str(v), va="center", fontsize=9, color=SOFT)
ax.set_xlabel("books kept after cleaning"); ax.set_title("Scraped catalogue by genre (510 books)", loc="left", weight="bold")
fig.tight_layout(); fig.savefig(os.path.join(OUT, "scrape_genres.png"), dpi=170); plt.close(fig)

# ---------------------------------------------------------------- context signal scatter
f = load_frames(connect())
stay = f["visits"].dropna(subset=["duration_min"]).groupby("member_id")["duration_min"].median()
pages = f["loans"].merge(f["books"][["book_id", "pages"]], on="book_id").groupby("member_id")["pages"] \
    .apply(lambda p: np.exp(np.log(p.clip(60, 1500)).mean()))
cnt = f["loans"].groupby("member_id").size()
df = pd.concat([stay.rename("stay"), pages.rename("pages"), cnt.rename("n")], axis=1).dropna()
df = df[df.n >= 2]
slope, intercept = np.polyfit(np.log(df.stay), np.log(df.pages), 1)
fig, ax = plt.subplots(figsize=(7.5, 5))
ax.scatter(df.stay, df.pages, s=16, alpha=0.55, color=GREEN, label="members (≥ 2 loans)")
xs = np.linspace(df.stay.min(), df.stay.max(), 100)
ax.plot(xs, np.exp(intercept + slope * np.log(xs)), color=BRASS, lw=2.5,
        label=f"fit: pages ∝ stay^{slope:.2f}   (r = {np.corrcoef(np.log(df.stay), np.log(df.pages))[0, 1]:.2f})")
ax.set_xscale("log"); ax.set_yscale("log")
ax.set_xlabel("median stay per visit (minutes, log scale)"); ax.set_ylabel("typical length of borrowed books (pages, log)")
ax.set_title("Gate context: visit length predicts book length", loc="left", weight="bold"); ax.legend(frameon=False)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "context_fit.png"), dpi=170); plt.close(fig)

# ---------------------------------------------------------------- recommender comparison
names = {"context": "Gate-context hybrid\n(proposed)", "hybrid": "Hybrid", "content": "Content-based",
         "user_cf": "User CF", "item_cf": "Item CF", "svd": "Matrix fact.", "popular": "Popularity"}
m = res["rec"]
keys = list(names)
x = np.arange(len(keys)); w = 0.38
fig, ax = plt.subplots(figsize=(10, 4.6))
b1 = ax.bar(x - w / 2, [m[k]["ndcg"] for k in keys], w, color=[BRASS if k == "context" else GREEN for k in keys], label="NDCG@10")
b2 = ax.bar(x + w / 2, [m[k]["recall"] / 2 for k in keys], w, color=BLUE, alpha=0.75, label="Recall@10 ÷ 2")
for r, k in zip(b1, keys):
    ax.text(r.get_x() + r.get_width() / 2, r.get_height() + 0.001, f"{m[k]['ndcg']:.3f}", ha="center", fontsize=8.5)
ax.set_xticks(x); ax.set_xticklabels([names[k] for k in keys], fontsize=9)
ax.set_title(f"Recommender evaluation on held-out loans ({res['rec_users']} members)", loc="left", weight="bold")
ax.legend(frameon=False)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "rec_compare.png"), dpi=170); plt.close(fig)

# ---------------------------------------------------------------- model comparison (regression + classification)
fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4.2))
fc = res["forecast"]
a1.bar([n.replace(" Regression", "\nregression") for n, *_ in fc], [r2 for _, r2, *_ in fc],
       color=[GREEN, GREEN, BRASS])
a1.axhline(0, color=SOFT, lw=0.8)
for i, (_, r2, *_ ) in enumerate(fc):
    a1.text(i, r2 + (0.02 if r2 >= 0 else -0.06), f"{r2:.2f}", ha="center", fontsize=9)
a1.set_title("Footfall forecast: R² on last 14 days", loc="left", weight="bold")
cl = res["classify"]
xx = np.arange(len(cl))
a2.bar(xx - 0.2, [c[4] for c in cl], 0.4, color=GREEN, label="F1")
a2.bar(xx + 0.2, [c[5] for c in cl], 0.4, color=BRASS, label="ROC-AUC")
a2.set_xticks(xx); a2.set_xticklabels([c[0].replace(" ", "\n", 1) for c in cl], fontsize=9)
a2.set_ylim(0, 0.85); a2.legend(frameon=False, loc="upper right")
a2.set_title("Late-return classifiers (test set)", loc="left", weight="bold")
fig.tight_layout(); fig.savefig(os.path.join(OUT, "model_compare.png"), dpi=170); plt.close(fig)
print("figures written to", OUT)
