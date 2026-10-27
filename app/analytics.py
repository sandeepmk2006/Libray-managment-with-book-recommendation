"""Analytics & ML module for the Athenaeum library-management system.

Implements five analysis functions mapping to university syllabus topics:
  - eda(frames)        → Module 2: Understanding Data (import, select, filter,
                         sort, group, rank, missing-value analysis, descriptive stats)
  - hypothesis(frames) → Module 3: Statistical Inference (hypothesis testing,
                         confidence intervals, effect sizes)
  - forecast(frames)   → Module 4: Machine Learning – Regression (linear,
                         polynomial, multiple linear; train/test split, metrics)
  - classify(frames)   → Module 4: Machine Learning – Classification (logistic
                         regression, KNN, decision tree, random forest; CV, ROC)
  - clusters(frames)   → Module 4: Machine Learning – Unsupervised (KMeans,
                         agglomerative, PCA, elbow/silhouette, dendrogram)
  - predict_late()     → Module 4: Explainable prediction endpoint

All functions accept the dict returned by ``app.db.load_frames(conn)`` and
return a plain-Python dict that is directly JSON-serialisable (no numpy types,
no NaN/Inf – replaced by None; floats rounded to 4 dp).
"""

import math
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from scipy import stats
from scipy.cluster.hierarchy import linkage, dendrogram as _dendrogram
from sklearn.cluster import KMeans, AgglomerativeClustering
from sklearn.decomposition import PCA
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import (
    accuracy_score, confusion_matrix, f1_score, mean_absolute_error,
    mean_squared_error, precision_score, r2_score, recall_score,
    roc_auc_score, roc_curve, silhouette_score, adjusted_rand_score,
)
from sklearn.model_selection import (
    StratifiedKFold, cross_val_score, train_test_split,
)
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import PolynomialFeatures, StandardScaler
from sklearn.tree import DecisionTreeClassifier, export_text

# ---------------------------------------------------------------------------
# Module-level cache for predict_late
# ---------------------------------------------------------------------------
_predict_cache: dict = {}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean(obj):
    """Recursively convert numpy types and replace NaN/inf with None."""
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        v = float(obj)
        if math.isnan(v) or math.isinf(v):
            return None
        return round(v, 4)
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return round(obj, 4)
    if isinstance(obj, np.ndarray):
        return _clean(obj.tolist())
    if isinstance(obj, (pd.Timestamp, datetime)):
        return obj.isoformat()
    return obj


def _desc(s: pd.Series) -> dict:
    """Descriptive statistics for a numeric Series (drop NaN first)."""
    s = s.dropna()
    if len(s) == 0:
        return {k: None for k in
                ("count", "mean", "median", "std", "var", "min",
                 "q1", "q3", "max", "skew", "kurtosis")}
    return {
        "count": int(len(s)),
        "mean": float(s.mean()),
        "median": float(s.median()),
        "std": float(s.std()),
        "var": float(s.var()),
        "min": float(s.min()),
        "q1": float(s.quantile(0.25)),
        "q3": float(s.quantile(0.75)),
        "max": float(s.max()),
        "skew": float(s.skew()),
        "kurtosis": float(s.kurtosis()),
    }


# ═══════════════════════════════════════════════════════════════════════════
# 1. EDA  –  Module 2: Understanding Data
# ═══════════════════════════════════════════════════════════════════════════

def eda(frames: dict) -> dict:
    """Exploratory data analysis: descriptive stats, distributions, groupings."""
    visits = frames["visits"].copy()
    loans = frames["loans"].copy()
    books = frames["books"]
    members = frames["members"]
    ratings = frames["ratings"]

    completed_visits = visits.dropna(subset=["exit_time"])

    # --- summary (per-table) ---
    summary_tables = {}
    for name, df in frames.items():
        missing = {c: int(df[c].isna().sum()) for c in df.columns if df[c].isna().sum() > 0}
        summary_tables[name] = {"rows": len(df), "cols": len(df.columns), "missing": missing}

    # --- descriptive stats ---
    loans_per_member = loans.groupby("member_id").size()
    returned_loans = loans.dropna(subset=["returned"])
    describe = {
        "duration_min": _desc(completed_visits["duration_min"]),
        "loans_per_member": _desc(loans_per_member),
        "rating": _desc(ratings["rating"]),
        "pages": _desc(books["pages"]),
        "days_late": _desc(returned_loans["days_late"]),
    }

    # --- hourly histogram (24 bins, entry_time hour) ---
    hourly = [0] * 24
    hours = completed_visits["entry_time"].dt.hour
    for h, cnt in hours.value_counts().items():
        hourly[int(h)] = int(cnt)

    # --- 7 × 24 weekday-hour matrix ---
    completed_visits = completed_visits.copy()
    completed_visits["weekday"] = completed_visits["entry_time"].dt.weekday
    completed_visits["hour"] = completed_visits["entry_time"].dt.hour
    wh = completed_visits.groupby(["weekday", "hour"]).size().unstack(fill_value=0)
    wh = wh.reindex(index=range(7), columns=range(24), fill_value=0)
    weekday_hour = wh.values.tolist()

    # --- daily series ---
    completed_visits["date"] = completed_visits["entry_time"].dt.date
    daily_g = completed_visits.groupby("date").agg(
        visits=("visit_id", "count"),
        unique_members=("member_id", "nunique"),
        avg_stay=("duration_min", "mean"),
    ).reset_index()
    daily = [{"date": str(r["date"]), "visits": int(r["visits"]),
              "unique_members": int(r["unique_members"]),
              "avg_stay": float(r["avg_stay"])} for _, r in daily_g.iterrows()]

    # --- by department ---
    vm = completed_visits.merge(members[["member_id", "department"]], on="member_id", how="left")
    dept_visits = vm.groupby("department").agg(
        visits=("visit_id", "count"), avg_stay=("duration_min", "mean")).reset_index()
    lm = loans.merge(members[["member_id", "department"]], on="member_id", how="left")
    dept_loans = lm.groupby("department").agg(loans=("loan_id", "count")).reset_index()
    ret_lm = returned_loans.merge(members[["member_id", "department"]], on="member_id", how="left")
    dept_late = ret_lm.groupby("department")["is_late"].mean().reset_index()
    dept_late.columns = ["department", "late_rate"]
    by_dept = dept_visits.merge(dept_loans, on="department", how="left").merge(
        dept_late, on="department", how="left")
    by_dept = by_dept.fillna(0)
    by_department = [{"department": r["department"], "visits": int(r["visits"]),
                      "avg_stay": float(r["avg_stay"]), "loans": int(r["loans"]),
                      "late_rate": float(r["late_rate"])}
                     for _, r in by_dept.iterrows()]

    # --- by purpose ---
    purpose_counts = visits["purpose"].value_counts(dropna=False).reset_index()
    purpose_counts.columns = ["purpose", "count"]
    purpose_counts["purpose"] = purpose_counts["purpose"].where(
        purpose_counts["purpose"].notna(), "Unknown")
    by_purpose = [{"purpose": str(r["purpose"]), "count": int(r["count"])}
                  for _, r in purpose_counts.iterrows()]

    # --- genre popularity ---
    lb = loans.merge(books[["book_id", "genre"]], on="book_id", how="left")
    genre_loans = lb.groupby("genre").agg(loans=("loan_id", "count")).reset_index()
    rb = ratings.merge(books[["book_id", "genre"]], on="book_id", how="left")
    genre_rat = rb.groupby("genre")["rating"].mean().reset_index()
    genre_rat.columns = ["genre", "avg_rating"]
    gp = genre_loans.merge(genre_rat, on="genre", how="left").fillna(0)
    gp = gp.sort_values("loans", ascending=False)
    genre_popularity = [{"genre": r["genre"], "loans": int(r["loans"]),
                         "avg_rating": float(r["avg_rating"])}
                        for _, r in gp.iterrows()]

    # --- top books (ranked by loans) ---
    book_loans = loans.groupby("book_id").agg(loans=("loan_id", "count")).reset_index()
    book_rat = ratings.groupby("book_id")["rating"].mean().reset_index()
    book_rat.columns = ["book_id", "avg_rating"]
    tb = book_loans.merge(book_rat, on="book_id", how="left").merge(
        books[["book_id", "title"]], on="book_id", how="left").fillna(0)
    tb = tb.sort_values("loans", ascending=False).head(20)
    top_books = [{"book_id": int(r["book_id"]), "title": r["title"],
                  "loans": int(r["loans"]), "avg_rating": float(r["avg_rating"])}
                 for _, r in tb.iterrows()]

    # --- Pearson correlation matrix (member-level features) ---
    m_visits = completed_visits.groupby("member_id").agg(
        visits=("visit_id", "count"), avg_stay=("duration_min", "mean")).reset_index()
    m_loans = loans.groupby("member_id").agg(loans=("loan_id", "count")).reset_index()
    m_late = returned_loans.groupby("member_id")["is_late"].mean().reset_index()
    m_late.columns = ["member_id", "late_rate"]
    m_rat = ratings.groupby("member_id")["rating"].mean().reset_index()
    m_rat.columns = ["member_id", "avg_rating"]
    mf = members[["member_id", "year"]].merge(m_visits, on="member_id", how="left") \
        .merge(m_loans, on="member_id", how="left") \
        .merge(m_late, on="member_id", how="left") \
        .merge(m_rat, on="member_id", how="left").fillna(0)
    corr_cols = ["visits", "avg_stay", "loans", "late_rate", "avg_rating", "year"]
    corr_matrix = mf[corr_cols].corr(method="pearson")
    correlation = {
        "columns": corr_cols,
        "matrix": corr_matrix.values.tolist(),
    }

    # --- stay histogram ---
    dur = completed_visits["duration_min"].dropna()
    counts_arr, bin_edges = np.histogram(dur, bins=20)
    stay_histogram = {"bins": bin_edges.tolist(), "counts": counts_arr.tolist()}

    # --- IQR outliers ---
    q1 = float(dur.quantile(0.25))
    q3 = float(dur.quantile(0.75))
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    outlier_count = int(((dur < lower) | (dur > upper)).sum())
    outliers = {"method": "IQR", "lower": lower, "upper": upper, "count": outlier_count}

    return _clean({
        "summary": summary_tables,
        "describe": describe,
        "hourly": hourly,
        "weekday_hour": weekday_hour,
        "daily": daily,
        "by_department": by_department,
        "by_purpose": by_purpose,
        "genre_popularity": genre_popularity,
        "top_books": top_books,
        "correlation": correlation,
        "stay_histogram": stay_histogram,
        "outliers": outliers,
    })


# ═══════════════════════════════════════════════════════════════════════════
# 2. HYPOTHESIS TESTING  –  Module 3: Statistical Inference
# ═══════════════════════════════════════════════════════════════════════════

def hypothesis(frames: dict) -> dict:
    """Statistical hypothesis tests with effect sizes and confidence intervals."""
    visits = frames["visits"].dropna(subset=["exit_time"]).copy()
    loans = frames["loans"].copy()
    members = frames["members"]
    ratings = frames["ratings"]
    returned = loans.dropna(subset=["returned"]).copy()

    visits["weekday"] = visits["entry_time"].dt.weekday
    visits["is_weekend"] = visits["weekday"] >= 5

    vm = visits.merge(members[["member_id", "department", "year", "gender"]],
                      on="member_id", how="left")
    lm = returned.merge(members[["member_id", "department", "year", "gender"]],
                         on="member_id", how="left")

    alpha = 0.05
    tests = []

    # (a) Welch t-test: stay duration weekday vs weekend
    wd = vm.loc[~vm["is_weekend"], "duration_min"].dropna()
    we = vm.loc[vm["is_weekend"], "duration_min"].dropna()
    t_stat, p_val = stats.ttest_ind(wd, we, equal_var=False)
    pooled_std = np.sqrt((wd.var() + we.var()) / 2)
    d = (wd.mean() - we.mean()) / pooled_std if pooled_std > 0 else 0
    tests.append({
        "name": "weekday_vs_weekend_stay",
        "question": "Do students stay longer on weekdays than weekends?",
        "h0": "Mean stay duration is the same on weekdays and weekends",
        "h1": "Mean stay duration differs between weekdays and weekends",
        "test": "Welch t-test",
        "statistic": float(t_stat),
        "p_value": float(p_val),
        "alpha": alpha,
        "decision": "Reject H0" if p_val < alpha else "Fail to reject H0",
        "effect_size": float(d),
        "interpretation": f"The mean weekday stay ({wd.mean():.1f} min) "
                          f"{'differs' if p_val < alpha else 'does not differ'} "
                          f"significantly from the weekend stay ({we.mean():.1f} min) "
                          f"(p={p_val:.4f}, Cohen's d={d:.3f}).",
    })

    # (b) One-way ANOVA: stay across departments
    dept_groups = [g["duration_min"].dropna().values
                   for _, g in vm.groupby("department")]
    dept_groups = [g for g in dept_groups if len(g) >= 2]
    f_stat, p_val = stats.f_oneway(*dept_groups)
    # eta-squared
    all_vals = np.concatenate(dept_groups)
    grand_mean = all_vals.mean()
    ss_between = sum(len(g) * (g.mean() - grand_mean) ** 2 for g in dept_groups)
    ss_total = np.sum((all_vals - grand_mean) ** 2)
    eta_sq = ss_between / ss_total if ss_total > 0 else 0
    tests.append({
        "name": "anova_stay_by_department",
        "question": "Does average stay duration differ across departments?",
        "h0": "Mean stay is the same across all departments",
        "h1": "At least one department has a different mean stay",
        "test": "One-way ANOVA",
        "statistic": float(f_stat),
        "p_value": float(p_val),
        "alpha": alpha,
        "decision": "Reject H0" if p_val < alpha else "Fail to reject H0",
        "effect_size": float(eta_sq),
        "interpretation": f"Stay duration {'varies' if p_val < alpha else 'does not vary'} "
                          f"significantly across departments "
                          f"(F={f_stat:.2f}, p={p_val:.4f}, η²={eta_sq:.3f}).",
    })

    # (c) Chi-square independence: department × purpose
    vm_purpose = vm.dropna(subset=["purpose"])
    ct = pd.crosstab(vm_purpose["department"], vm_purpose["purpose"])
    chi2, p_val, dof, _ = stats.chi2_contingency(ct)
    n = ct.values.sum()
    k = min(ct.shape) - 1
    cramers_v = np.sqrt(chi2 / (n * k)) if (n * k) > 0 else 0
    tests.append({
        "name": "chi2_department_purpose",
        "question": "Is there an association between department and visit purpose?",
        "h0": "Department and purpose are independent",
        "h1": "Department and purpose are associated",
        "test": "Chi-square test of independence",
        "statistic": float(chi2),
        "p_value": float(p_val),
        "alpha": alpha,
        "decision": "Reject H0" if p_val < alpha else "Fail to reject H0",
        "effect_size": float(cramers_v),
        "interpretation": f"Department and visit purpose "
                          f"{'are' if p_val < alpha else 'are not'} significantly "
                          f"associated (χ²={chi2:.2f}, p={p_val:.4f}, "
                          f"Cramér's V={cramers_v:.3f}).",
    })

    # (d) Pearson & Spearman correlation: visits vs loans
    m_visits = visits.groupby("member_id").size().reset_index(name="n_visits")
    m_loans = loans.groupby("member_id").size().reset_index(name="n_loans")
    ml = m_visits.merge(m_loans, on="member_id", how="inner")
    if len(ml) >= 3:
        r_p, p_p = stats.pearsonr(ml["n_visits"], ml["n_loans"])
        r_s, p_s = stats.spearmanr(ml["n_visits"], ml["n_loans"])
    else:
        r_p, p_p, r_s, p_s = 0, 1, 0, 1
    tests.append({
        "name": "correlation_visits_loans",
        "question": "Are the number of visits and loans per member correlated?",
        "h0": "There is no linear correlation between visits and loans",
        "h1": "There is a significant correlation between visits and loans",
        "test": "Pearson correlation",
        "statistic": float(r_p),
        "p_value": float(p_p),
        "alpha": alpha,
        "decision": "Reject H0" if p_p < alpha else "Fail to reject H0",
        "effect_size": float(r_p),
        "interpretation": f"Visits and loans per member show a "
                          f"{'significant' if p_p < alpha else 'non-significant'} "
                          f"Pearson correlation of r={r_p:.3f} (p={p_p:.4f}).",
    })
    tests.append({
        "name": "spearman_visits_loans",
        "question": "Is there a monotonic relationship between visits and loans?",
        "h0": "No monotonic association between visits and loans",
        "h1": "Significant monotonic association exists",
        "test": "Spearman rank correlation",
        "statistic": float(r_s),
        "p_value": float(p_s),
        "alpha": alpha,
        "decision": "Reject H0" if p_s < alpha else "Fail to reject H0",
        "effect_size": float(r_s),
        "interpretation": f"Spearman ρ={r_s:.3f} (p={p_s:.4f}) indicates a "
                          f"{'significant' if p_s < alpha else 'non-significant'} "
                          f"monotonic relationship.",
    })

    # (e) Mann-Whitney: days_late first-year vs others
    fy = lm.loc[lm["year"] == 1, "days_late"].dropna()
    oth = lm.loc[lm["year"] != 1, "days_late"].dropna()
    if len(fy) >= 1 and len(oth) >= 1:
        u_stat, p_val = stats.mannwhitneyu(fy, oth, alternative="two-sided")
        # rank-biserial as effect size
        r_rb = 1 - (2 * u_stat) / (len(fy) * len(oth)) if (len(fy) * len(oth)) > 0 else 0
    else:
        u_stat, p_val, r_rb = 0, 1, 0
    tests.append({
        "name": "mannwhitney_late_firstyear",
        "question": "Do first-year students return books later than others?",
        "h0": "Distribution of days_late is the same for first-year and others",
        "h1": "Distributions differ (first-year students return later)",
        "test": "Mann-Whitney U",
        "statistic": float(u_stat),
        "p_value": float(p_val),
        "alpha": alpha,
        "decision": "Reject H0" if p_val < alpha else "Fail to reject H0",
        "effect_size": float(r_rb),
        "interpretation": f"First-year students' late days (median={fy.median():.1f}) "
                          f"{'differ' if p_val < alpha else 'do not differ'} "
                          f"significantly from others (median={oth.median():.1f}), "
                          f"U={u_stat:.0f}, p={p_val:.4f}.",
    })

    # (f) Two-proportion z-test: late rate male vs female
    male = lm[lm["gender"] == "M"]
    female = lm[lm["gender"] == "F"]
    n1, n2 = len(male), len(female)
    x1 = int(male["is_late"].sum()) if n1 > 0 else 0
    x2 = int(female["is_late"].sum()) if n2 > 0 else 0
    p1 = x1 / n1 if n1 > 0 else 0
    p2 = x2 / n2 if n2 > 0 else 0
    p_pool = (x1 + x2) / (n1 + n2) if (n1 + n2) > 0 else 0
    se = np.sqrt(p_pool * (1 - p_pool) * (1/max(n1,1) + 1/max(n2,1))) if p_pool > 0 and p_pool < 1 else 1
    z_stat = (p1 - p2) / se if se > 0 else 0
    p_val = float(2 * stats.norm.sf(abs(z_stat)))
    tests.append({
        "name": "zprop_late_gender",
        "question": "Is the late return rate different for male vs female members?",
        "h0": "Late return rate is the same for males and females",
        "h1": "Late return rates differ by gender",
        "test": "Two-proportion z-test",
        "statistic": float(z_stat),
        "p_value": p_val,
        "alpha": alpha,
        "decision": "Reject H0" if p_val < alpha else "Fail to reject H0",
        "effect_size": None,
        "interpretation": f"Male late rate ({p1:.3f}) vs female ({p2:.3f}): "
                          f"{'significantly different' if p_val < alpha else 'no significant difference'} "
                          f"(z={z_stat:.3f}, p={p_val:.4f}).",
    })

    # (g) Shapiro-Wilk normality of stay
    sample = completed_visits_sample = vm["duration_min"].dropna()
    if len(sample) > 5000:
        sample = sample.sample(5000, random_state=42)
    w_stat, p_val = stats.shapiro(sample)
    tests.append({
        "name": "shapiro_stay_normality",
        "question": "Is the distribution of stay duration normal?",
        "h0": "Stay durations follow a normal distribution",
        "h1": "Stay durations do not follow a normal distribution",
        "test": "Shapiro-Wilk",
        "statistic": float(w_stat),
        "p_value": float(p_val),
        "alpha": alpha,
        "decision": "Reject H0" if p_val < alpha else "Fail to reject H0",
        "effect_size": None,
        "interpretation": f"Stay durations {'do not follow' if p_val < alpha else 'follow'} "
                          f"a normal distribution (W={w_stat:.4f}, p={p_val:.4f}).",
    })

    # --- Confidence intervals ---
    cis = []

    # CI for mean stay (t-interval)
    dur = vm["duration_min"].dropna()
    n = len(dur)
    mean_stay = float(dur.mean())
    se = float(dur.std() / np.sqrt(n)) if n > 1 else 0
    t_crit = float(stats.t.ppf(0.975, n - 1)) if n > 1 else 0
    cis.append({
        "metric": "mean_stay_min",
        "mean": mean_stay,
        "low": mean_stay - t_crit * se,
        "high": mean_stay + t_crit * se,
        "level": 0.95,
    })

    # CI for mean rating
    rat = ratings["rating"].dropna()
    n = len(rat)
    mean_r = float(rat.mean())
    se = float(rat.std() / np.sqrt(n)) if n > 1 else 0
    t_crit = float(stats.t.ppf(0.975, n - 1)) if n > 1 else 0
    cis.append({
        "metric": "mean_rating",
        "mean": mean_r,
        "low": mean_r - t_crit * se,
        "high": mean_r + t_crit * se,
        "level": 0.95,
    })

    # CI for late rate (Wilson interval)
    ret_all = returned.dropna(subset=["is_late"])
    n = len(ret_all)
    p_hat = float(ret_all["is_late"].mean()) if n > 0 else 0
    z = 1.96
    if n > 0:
        denom = 1 + z**2 / n
        centre = (p_hat + z**2 / (2 * n)) / denom
        margin = z * np.sqrt(p_hat * (1 - p_hat) / n + z**2 / (4 * n**2)) / denom
        cis.append({
            "metric": "late_rate",
            "mean": p_hat,
            "low": max(0, centre - margin),
            "high": min(1, centre + margin),
            "level": 0.95,
        })
    else:
        cis.append({"metric": "late_rate", "mean": 0, "low": 0, "high": 0, "level": 0.95})

    return _clean({"tests": tests, "confidence_intervals": cis})


# ═══════════════════════════════════════════════════════════════════════════
# 3. FORECAST  –  Module 4: Machine Learning (Regression)
# ═══════════════════════════════════════════════════════════════════════════

def forecast(frames: dict) -> dict:
    """Forecast hourly library footfall with linear, polynomial, and multiple
    linear regression models."""
    visits = frames["visits"].dropna(subset=["exit_time"]).copy()
    visits["date"] = visits["entry_time"].dt.date
    visits["hour"] = visits["entry_time"].dt.hour

    # Filter hours 8-20
    visits = visits[(visits["hour"] >= 8) & (visits["hour"] <= 20)]

    # Build hourly counts
    hourly = visits.groupby(["date", "hour"]).size().reset_index(name="count")
    hourly["date"] = pd.to_datetime(hourly["date"])
    hourly["weekday"] = hourly["date"].dt.weekday
    hourly["is_weekend"] = (hourly["weekday"] >= 5).astype(int)
    hourly = hourly.sort_values(["date", "hour"]).reset_index(drop=True)
    hourly["idx"] = np.arange(len(hourly))
    hourly["dt"] = hourly["date"] + pd.to_timedelta(hourly["hour"], unit="h")

    # Chronological train/test split (last 14 days)
    max_date = hourly["date"].max()
    split_date = max_date - pd.Timedelta(days=14)
    train = hourly[hourly["date"] <= split_date]
    test = hourly[hourly["date"] > split_date]

    if len(train) < 5 or len(test) < 2:
        # Fallback: use 80/20 split
        n_train = int(len(hourly) * 0.8)
        train = hourly.iloc[:n_train]
        test = hourly.iloc[n_train:]

    y_train, y_test = train["count"].values, test["count"].values
    models_out = []

    # --- Model 1: Simple Linear Regression (hour index trend) ---
    X_tr_lin = train[["idx"]].values
    X_te_lin = test[["idx"]].values
    lr = LinearRegression()
    lr.fit(X_tr_lin, y_train)
    pred_lin_test = lr.predict(X_te_lin)
    models_out.append({
        "name": "Linear Regression",
        "r2": float(r2_score(y_test, pred_lin_test)),
        "mae": float(mean_absolute_error(y_test, pred_lin_test)),
        "rmse": float(np.sqrt(mean_squared_error(y_test, pred_lin_test))),
        "coefficients": {"intercept": float(lr.intercept_),
                         "idx": float(lr.coef_[0])},
    })

    # --- Model 2: Polynomial Regression (degree 3 on hour-of-day) ---
    poly = PolynomialFeatures(degree=3, include_bias=False)
    X_tr_poly = poly.fit_transform(train[["hour"]].values)
    X_te_poly = poly.transform(test[["hour"]].values)
    pr = LinearRegression()
    pr.fit(X_tr_poly, y_train)
    pred_poly_test = pr.predict(X_te_poly)
    poly_names = [f"hour^{i+1}" for i in range(X_tr_poly.shape[1])]
    models_out.append({
        "name": "Polynomial Regression",
        "r2": float(r2_score(y_test, pred_poly_test)),
        "mae": float(mean_absolute_error(y_test, pred_poly_test)),
        "rmse": float(np.sqrt(mean_squared_error(y_test, pred_poly_test))),
        "coefficients": {**{"intercept": float(pr.intercept_)},
                         **{n: float(c) for n, c in zip(poly_names, pr.coef_)}},
    })

    # --- Model 3: Multiple Linear Regression ---
    # Features: hour poly(3) + weekday + is_weekend + lag/rolling features
    hourly_sorted = hourly.sort_values(["date", "hour"]).copy()
    hourly_sorted["lag_24"] = hourly_sorted["count"].shift(24).fillna(
        hourly_sorted["count"].mean())
    hourly_sorted["rolling_mean"] = hourly_sorted["count"].rolling(
        24, min_periods=1).mean()

    train_m = hourly_sorted[hourly_sorted["date"] <= split_date]
    test_m = hourly_sorted[hourly_sorted["date"] > split_date]

    if len(train_m) < 5:
        n_train = int(len(hourly_sorted) * 0.8)
        train_m = hourly_sorted.iloc[:n_train]
        test_m = hourly_sorted.iloc[n_train:]

    feat_cols_m = ["hour", "weekday", "is_weekend", "lag_24", "rolling_mean"]
    poly_m = PolynomialFeatures(degree=3, include_bias=False)

    def _build_multi_X(df):
        hp = poly_m.fit_transform(df[["hour"]].values) if not hasattr(poly_m, "n_output_features_") \
            else poly_m.transform(df[["hour"]].values)
        other = df[["weekday", "is_weekend", "lag_24", "rolling_mean"]].values
        return np.hstack([hp, other])

    poly_m.fit(train_m[["hour"]].values)
    X_tr_m = _build_multi_X(train_m)
    X_te_m = _build_multi_X(test_m)
    y_tr_m = train_m["count"].values
    y_te_m = test_m["count"].values

    mlr = LinearRegression()
    mlr.fit(X_tr_m, y_tr_m)
    pred_multi_test = mlr.predict(X_te_m)
    multi_names = [f"hour^{i+1}" for i in range(poly_m.n_output_features_)] + \
                  ["weekday", "is_weekend", "lag_24", "rolling_mean"]
    models_out.append({
        "name": "Multiple Linear Regression",
        "r2": float(r2_score(y_te_m, pred_multi_test)),
        "mae": float(mean_absolute_error(y_te_m, pred_multi_test)),
        "rmse": float(np.sqrt(mean_squared_error(y_te_m, pred_multi_test))),
        "coefficients": {**{"intercept": float(mlr.intercept_)},
                         **{n: float(c) for n, c in zip(multi_names, mlr.coef_)}},
    })

    # Best model by R²
    best_idx = max(range(len(models_out)), key=lambda i: models_out[i]["r2"])
    best_name = models_out[best_idx]["name"]

    # --- next_24h predictions from the best model ---
    last_dt = hourly_sorted["dt"].max()
    next_hours = []
    for i in range(1, 25):
        ndt = last_dt + pd.Timedelta(hours=i)
        h = ndt.hour
        if h < 8 or h > 20:
            continue
        wd = ndt.weekday()
        is_we = 1 if wd >= 5 else 0
        row = {
            "hour": h, "weekday": wd, "is_weekend": is_we,
            "idx": hourly_sorted["idx"].max() + i,
            "lag_24": float(hourly_sorted["count"].iloc[-24 + i]
                           if i <= 24 and len(hourly_sorted) >= 24
                           else hourly_sorted["count"].mean()),
            "rolling_mean": float(hourly_sorted["count"].tail(24).mean()),
        }
        next_hours.append((ndt, row))

    next_24h = []
    for ndt, row in next_hours:
        if best_name == "Linear Regression":
            pred = lr.predict([[row["idx"]]])[0]
        elif best_name == "Polynomial Regression":
            pred = pr.predict(poly.transform([[row["hour"]]]))[0]
        else:
            hp = poly_m.transform([[row["hour"]]])
            x = np.hstack([hp, [[row["weekday"], row["is_weekend"],
                                  row["lag_24"], row["rolling_mean"]]]])
            pred = mlr.predict(x)[0]
        next_24h.append({
            "hour_iso": ndt.isoformat(),
            "predicted": max(0, float(pred)),
        })

    # --- actual_vs_pred for last 3 days of test ---
    if len(test_m) > 0:
        last3_date = test_m["date"].max() - pd.Timedelta(days=2)
        avp_data = test_m[test_m["date"] >= last3_date].copy()
    else:
        avp_data = test.tail(30).copy()

    actual_vs_pred = []
    for _, row in avp_data.iterrows():
        dt_str = row["dt"].isoformat() if hasattr(row["dt"], "isoformat") else str(row["dt"])
        lin_p = float(lr.predict([[row["idx"]]])[0])
        poly_p = float(pr.predict(poly.transform([[row["hour"]]]))[0])
        hp = poly_m.transform([[row["hour"]]])
        lag = row.get("lag_24", hourly_sorted["count"].mean())
        rm = row.get("rolling_mean", hourly_sorted["count"].mean())
        x_m = np.hstack([hp, [[row["weekday"], row["is_weekend"], lag, rm]]])
        multi_p = float(mlr.predict(x_m)[0])
        actual_vs_pred.append({
            "x": dt_str,
            "actual": int(row["count"]),
            "linear": max(0, lin_p),
            "polynomial": max(0, poly_p),
            "multiple": max(0, multi_p),
        })

    return _clean({
        "target": "hourly footfall",
        "models": models_out,
        "best": best_name,
        "next_24h": next_24h,
        "actual_vs_pred": actual_vs_pred,
    })


# ═══════════════════════════════════════════════════════════════════════════
# 4. CLASSIFY  –  Module 4: Machine Learning (Classification)
# ═══════════════════════════════════════════════════════════════════════════

def _build_classification_features(frames):
    """Build feature matrix for late-return classification (no data leakage)."""
    loans = frames["loans"].copy()
    members = frames["members"]
    books = frames["books"]
    visits = frames["visits"].dropna(subset=["exit_time"]).copy()

    # Only returned loans with known is_late
    returned = loans.dropna(subset=["returned"]).copy()
    returned = returned[returned["is_late"].notna()].copy()
    returned["is_late_int"] = returned["is_late"].astype(int)
    returned = returned.sort_values("issued").reset_index(drop=True)

    # Merge member info
    returned = returned.merge(members[["member_id", "department", "year", "gender"]],
                              on="member_id", how="left")
    returned = returned.merge(books[["book_id", "pages"]], on="book_id", how="left")
    returned["is_first_year"] = (returned["year"] == 1).astype(int)
    returned["issue_weekday"] = returned["issued"].dt.weekday

    # Member avg_stay
    m_stay = visits.groupby("member_id")["duration_min"].mean().reset_index()
    m_stay.columns = ["member_id", "member_avg_stay"]
    returned = returned.merge(m_stay, on="member_id", how="left")
    returned["member_avg_stay"] = returned["member_avg_stay"].fillna(
        returned["member_avg_stay"].median() if returned["member_avg_stay"].notna().any() else 0)

    # Member visits per week
    visits_range = (visits["entry_time"].max() - visits["entry_time"].min()).days or 1
    m_vpw = visits.groupby("member_id").size().reset_index(name="total_visits")
    m_vpw["visits_per_week"] = m_vpw["total_visits"] * 7.0 / visits_range
    returned = returned.merge(m_vpw[["member_id", "visits_per_week"]],
                              on="member_id", how="left")
    returned["visits_per_week"] = returned["visits_per_week"].fillna(0)

    # Past loan count and past late rate (NO LEAKAGE: only loans before current)
    # Vectorised: within each member group (sorted by issued), use cumcount and
    # expanding mean of is_late shifted by 1 row.
    returned = returned.sort_values(["member_id", "issued"]).reset_index(drop=True)
    returned["member_past_loan_count"] = returned.groupby("member_id").cumcount()
    shifted_late = returned.groupby("member_id")["is_late_int"].transform(
        lambda s: s.expanding().mean().shift(1))
    returned["member_past_late_rate"] = shifted_late.fillna(0)

    # Department one-hot
    dept_dummies = pd.get_dummies(returned["department"], prefix="dept")
    returned = pd.concat([returned, dept_dummies], axis=1)

    # Feature columns
    base_features = ["year", "is_first_year", "pages", "member_past_loan_count",
                     "member_past_late_rate", "issue_weekday", "member_avg_stay",
                     "visits_per_week"]
    dept_cols = [c for c in dept_dummies.columns]
    feature_cols = base_features + dept_cols

    # Fill NaN in pages
    returned["pages"] = returned["pages"].fillna(returned["pages"].median()
                                                  if returned["pages"].notna().any() else 200)

    X = returned[feature_cols].values.astype(float)
    y = returned["is_late_int"].values
    return X, y, feature_cols, returned


def classify(frames: dict) -> dict:
    """Classification of late returns with multiple models, CV, and ROC."""
    X, y, feature_cols, returned = _build_classification_features(frames)

    late_count = int(y.sum())
    on_time_count = int(len(y) - late_count)

    # Stratified split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y)

    scaler = StandardScaler()
    X_train_sc = scaler.fit_transform(X_train)
    X_test_sc = scaler.transform(X_test)

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    models = {}
    roc_data = {}
    results = []

    # Logistic Regression
    log_reg = LogisticRegression(random_state=42, max_iter=1000, solver="lbfgs", class_weight="balanced")
    log_reg.fit(X_train_sc, y_train)
    models["Logistic Regression"] = (log_reg, X_test_sc)

    # KNN (tune k via CV)
    best_k, best_cv_score = 3, 0
    for k in range(3, 16, 2):
        knn_temp = KNeighborsClassifier(n_neighbors=k)
        sc = cross_val_score(knn_temp, X_train_sc, y_train, cv=cv, scoring="accuracy").mean()
        if sc > best_cv_score:
            best_k, best_cv_score = k, sc
    knn = KNeighborsClassifier(n_neighbors=best_k)
    knn.fit(X_train_sc, y_train)
    models["KNN"] = (knn, X_test_sc)

    # Decision Tree (tune max_depth)
    best_depth, best_dt_score = 3, 0
    for d in range(2, 11):
        dt_temp = DecisionTreeClassifier(max_depth=d, random_state=42, class_weight="balanced")
        sc = cross_val_score(dt_temp, X_train, y_train, cv=cv, scoring="accuracy").mean()
        if sc > best_dt_score:
            best_depth, best_dt_score = d, sc
    dt = DecisionTreeClassifier(max_depth=best_depth, random_state=42, class_weight="balanced")
    dt.fit(X_train, y_train)
    models["Decision Tree"] = (dt, X_test)

    # Random Forest
    rf = RandomForestClassifier(class_weight="balanced", n_estimators=100, max_depth=best_depth + 2,
                                random_state=42, n_jobs=-1)
    rf.fit(X_train, y_train)
    models["Random Forest"] = (rf, X_test)

    for name, (model, X_te) in models.items():
        pred = model.predict(X_te)
        prob = model.predict_proba(X_te)[:, 1] if hasattr(model, "predict_proba") else pred.astype(float)
        # CV on appropriate X
        X_cv = X_train_sc if name in ("Logistic Regression", "KNN") else X_train
        cv_scores = cross_val_score(model, X_cv, y_train, cv=cv, scoring="accuracy")

        cm = confusion_matrix(y_test, pred)
        tn, fp, fn, tp = cm.ravel() if cm.size == 4 else (0, 0, 0, 0)

        fpr, tpr, _ = roc_curve(y_test, prob)
        # Downsample ROC to ≤50 points
        if len(fpr) > 50:
            idx = np.linspace(0, len(fpr) - 1, 50, dtype=int)
            fpr, tpr = fpr[idx], tpr[idx]
        roc_data[name] = {"fpr": fpr.tolist(), "tpr": tpr.tolist()}

        results.append({
            "name": name,
            "accuracy": float(accuracy_score(y_test, pred)),
            "precision": float(precision_score(y_test, pred, zero_division=0)),
            "recall": float(recall_score(y_test, pred, zero_division=0)),
            "f1": float(f1_score(y_test, pred, zero_division=0)),
            "roc_auc": float(roc_auc_score(y_test, prob)),
            "confusion": [[int(tn), int(fp)], [int(fn), int(tp)]],
            "cv_mean": float(cv_scores.mean()),
            "cv_std": float(cv_scores.std()),
        })

    # Best model by f1
    best_name = max(results, key=lambda r: r["f1"])["name"]

    # Feature importance (from tree / forest)
    importances = rf.feature_importances_
    fi = sorted(
        [{"feature": f, "importance": float(imp)}
         for f, imp in zip(feature_cols, importances)],
        key=lambda x: -x["importance"])

    # Tree rules
    tree_rules = export_text(dt, feature_names=feature_cols, max_depth=3)

    return _clean({
        "target": "late return",
        "features": feature_cols,
        "class_balance": {"late": late_count, "on_time": on_time_count},
        "models": results,
        "best": best_name,
        "feature_importance": fi,
        "tree_rules": tree_rules,
        "roc": roc_data,
    })


def predict_late(frames: dict, member_id, book_id) -> dict:
    """Predict probability of late return for a member/book pair.

    Uses a logistic regression model cached at module level for efficiency.
    Returns probability, label, and top contributing factors for explainability.
    """
    global _predict_cache
    cache_key = "logistic_model"

    if cache_key not in _predict_cache:
        X, y, feature_cols, returned = _build_classification_features(frames)
        scaler = StandardScaler()
        X_sc = scaler.fit_transform(X)
        model = LogisticRegression(random_state=42, max_iter=1000, solver="lbfgs", class_weight="balanced")
        model.fit(X_sc, y)
        _predict_cache[cache_key] = (model, scaler, feature_cols, frames)

    model, scaler, feature_cols, _ = _predict_cache[cache_key]

    # Build features for this member/book
    members = frames["members"]
    books = frames["books"]
    loans = frames["loans"]
    visits = frames["visits"].dropna(subset=["exit_time"])
    returned_loans = loans.dropna(subset=["returned"]).copy()
    returned_loans["is_late_int"] = returned_loans["is_late"].fillna(False).astype(int)

    mem = members[members["member_id"] == member_id]
    book = books[books["book_id"] == book_id]

    year = int(mem["year"].iloc[0]) if len(mem) > 0 else 2
    is_first_year = 1 if year == 1 else 0
    pages = int(book["pages"].iloc[0]) if len(book) > 0 and pd.notna(book["pages"].iloc[0]) else 200
    dept = str(mem["department"].iloc[0]) if len(mem) > 0 else "CSE"

    # Past loans for this member
    m_loans = returned_loans[returned_loans["member_id"] == member_id]
    past_count = len(m_loans)
    past_late_rate = float(m_loans["is_late_int"].mean()) if past_count > 0 else 0

    # Visit stats
    m_visits = visits[visits["member_id"] == member_id]
    avg_stay = float(m_visits["duration_min"].mean()) if len(m_visits) > 0 else \
        float(visits["duration_min"].mean())

    visits_range = (visits["entry_time"].max() - visits["entry_time"].min()).days or 1
    vpw = len(m_visits) * 7.0 / visits_range

    issue_weekday = datetime.now().weekday()

    # Build feature vector
    base_vals = [year, is_first_year, pages, past_count, past_late_rate,
                 issue_weekday, avg_stay, vpw]
    # Department one-hot
    dept_features = {f: 0 for f in feature_cols if f.startswith("dept_")}
    dept_key = f"dept_{dept}"
    if dept_key in dept_features:
        dept_features[dept_key] = 1

    x = np.array(base_vals + list(dept_features.values()), dtype=float).reshape(1, -1)

    # Ensure correct number of features
    if x.shape[1] != len(feature_cols):
        # Pad or trim
        if x.shape[1] < len(feature_cols):
            x = np.hstack([x, np.zeros((1, len(feature_cols) - x.shape[1]))])
        else:
            x = x[:, :len(feature_cols)]

    x_sc = scaler.transform(x)
    prob = float(model.predict_proba(x_sc)[0, 1])
    label = "late" if prob >= 0.5 else "on_time"

    # Top factors: coefficient × scaled value
    coefs = model.coef_[0]
    contributions = coefs * x_sc[0]
    abs_contrib = np.abs(contributions)
    top_idx = abs_contrib.argsort()[::-1][:5]
    top_factors = [{"feature": feature_cols[i], "contribution": float(contributions[i])}
                   for i in top_idx]

    return _clean({
        "probability": prob,
        "label": label,
        "top_factors": top_factors,
    })


# ═══════════════════════════════════════════════════════════════════════════
# 5. CLUSTERS  –  Module 4: Machine Learning (Unsupervised Learning)
# ═══════════════════════════════════════════════════════════════════════════

def clusters(frames: dict) -> dict:
    """Member segmentation using KMeans and Agglomerative Clustering."""
    members = frames["members"]
    visits = frames["visits"].dropna(subset=["exit_time"]).copy()
    loans = frames["loans"].copy()
    ratings = frames["ratings"]
    returned = loans.dropna(subset=["returned"]).copy()
    returned["is_late_int"] = returned["is_late"].fillna(False).astype(int)

    # Visit-level features
    visits["weekday"] = visits["entry_time"].dt.weekday
    visits["is_weekend"] = (visits["weekday"] >= 5).astype(int)
    visits["entry_hour"] = visits["entry_time"].dt.hour

    visits_range_days = max((visits["entry_time"].max() - visits["entry_time"].min()).days, 1)
    weeks = visits_range_days / 7.0

    # Per-member aggregations
    m_visits = visits.groupby("member_id").agg(
        total_visits=("visit_id", "count"),
        avg_stay=("duration_min", "mean"),
        mean_entry_hour=("entry_hour", "mean"),
        weekend_share=("is_weekend", "mean"),
    ).reset_index()
    m_visits["visits_per_week"] = m_visits["total_visits"] / weeks

    m_loans = loans.groupby("member_id").agg(loans=("loan_id", "count")).reset_index()

    m_late = returned.groupby("member_id")["is_late_int"].mean().reset_index()
    m_late.columns = ["member_id", "late_rate"]

    m_rat = ratings.groupby("member_id")["rating"].mean().reset_index()
    m_rat.columns = ["member_id", "avg_rating"]

    # Genre diversity (entropy)
    lb = loans.merge(frames["books"][["book_id", "genre"]], on="book_id", how="left")
    def _entropy(s):
        p = s.value_counts(normalize=True)
        return float(-np.sum(p * np.log2(p + 1e-10)))
    m_genre_div = lb.groupby("member_id")["genre"].apply(_entropy).reset_index()
    m_genre_div.columns = ["member_id", "genre_diversity"]

    # Merge all
    mf = members[["member_id"]].merge(m_visits, on="member_id", how="left") \
        .merge(m_loans, on="member_id", how="left") \
        .merge(m_late, on="member_id", how="left") \
        .merge(m_rat, on="member_id", how="left") \
        .merge(m_genre_div, on="member_id", how="left")

    feature_names = ["visits_per_week", "avg_stay", "loans", "late_rate",
                     "avg_rating", "genre_diversity", "mean_entry_hour", "weekend_share"]
    # members who never rated / returned anything have no opinion or lateness record:
    # impute those with the population mean instead of 0 so they aren't read as "harsh" or "punctual"
    for f in ("avg_rating", "late_rate"):
        mf[f] = mf[f].fillna(mf[f].mean())
    for f in feature_names:
        mf[f] = mf[f].fillna(0)

    X = mf[feature_names].values.astype(float)
    member_ids = mf["member_id"].values

    scaler = StandardScaler()
    X_sc = scaler.fit_transform(X)

    # Elbow + silhouette for k=2..8
    elbow = []
    best_k, best_sil = 3, -1
    for k in range(2, 9):
        km = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = km.fit_predict(X_sc)
        sil = float(silhouette_score(X_sc, labels))
        elbow.append({"k": k, "inertia": float(km.inertia_), "silhouette": sil})
        # k=2 only splits members into "more" and "less"; require at least 3 personas
        if k >= 3 and sil > best_sil:
            best_k, best_sil = k, sil

    # Final KMeans
    km_final = KMeans(n_clusters=best_k, random_state=42, n_init=10)
    km_labels = km_final.fit_predict(X_sc)

    # PCA 2D projection
    pca = PCA(n_components=2, random_state=42)
    X_2d = pca.fit_transform(X_sc)

    points = [{"member_id": str(mid), "x": float(X_2d[i, 0]),
               "y": float(X_2d[i, 1]), "cluster": int(km_labels[i])}
              for i, mid in enumerate(member_ids)]

    # Centroid profiles with persona names
    _persona_words = {
        "visits_per_week": ("Frequent visitors", "Rare visitors"),
        "avg_stay": ("Long-stayers", "Quick visitors"),
        "loans": ("Heavy borrowers", "Light borrowers"),
        "late_rate": ("Late returners", "Punctual members"),
        "avg_rating": ("Generous raters", "Critical readers"),
        "genre_diversity": ("Genre explorers", "Genre specialists"),
        "mean_entry_hour": ("Night-owl readers", "Early-bird readers"),
        "weekend_share": ("Weekend regulars", "Weekday regulars"),
    }

    centroids_profile = []
    centroids_sc = km_final.cluster_centers_  # shape (k, n_features)
    for c in range(best_k):
        mask = km_labels == c
        size = int(mask.sum())
        profile = {"cluster": c, "size": size}
        for j, fn in enumerate(feature_names):
            profile[fn] = float(mf.loc[mask, fn].mean())

        # z-scores for persona naming
        z_scores = centroids_sc[c]
        top2_idx = np.abs(z_scores).argsort()[::-1][:2]
        parts = []
        for idx in top2_idx:
            fn = feature_names[idx]
            high_word, low_word = _persona_words.get(fn, (fn, fn))
            parts.append(high_word if z_scores[idx] > 0 else low_word)
        profile["persona"] = " & ".join(parts)
        centroids_profile.append(profile)

    # Agglomerative Clustering (ward)
    agg = AgglomerativeClustering(n_clusters=best_k, linkage="ward")
    agg_labels = agg.fit_predict(X_sc)
    agg_sil = float(silhouette_score(X_sc, agg_labels))
    ari = float(adjusted_rand_score(km_labels, agg_labels))

    # Dendrogram
    Z = linkage(X_sc, method="ward")
    dend = _dendrogram(Z, truncate_mode="lastp", p=20, no_plot=True)

    return _clean({
        "features": feature_names,
        "elbow": elbow,
        "chosen_k": best_k,
        "kmeans": {
            "points": points,
            "centroids_profile": centroids_profile,
        },
        "agglomerative": {
            "silhouette": agg_sil,
            "agreement_ari": ari,
            "dendrogram": {
                "icoord": dend["icoord"],
                "dcoord": dend["dcoord"],
                "labels": dend["ivl"],
            },
        },
    })


# ============================================================================
# Occupancy forecast (Module 4 regression applied to a real-time decision)
# ============================================================================
def occupancy_forecast(frames: dict, inside_now: int, capacity: int, forecast_result: dict = None) -> dict:
    """Predict how many people will be INSIDE each coming hour, and raise alerts.

    occupancy(h) = inside_now * S(h) + sum_j arrivals(j) * S(h - j + 0.5)
    where arrivals come from the best footfall regression and S(t) is the empirical
    survival function of stay length (share of visits still going after t hours).
    """
    fc = forecast_result or forecast(frames)
    stays_h = frames["visits"]["duration_min"].dropna().to_numpy() / 60.0
    surv = lambda t: float((stays_h > t).mean()) if t >= 0 else 1.0

    arrivals = [(pd.Timestamp(r["hour_iso"]), r["predicted"]) for r in fc["next_24h"]]
    out = []
    for k, (ts, _) in enumerate(arrivals):
        hours_from_now = (ts - arrivals[0][0]).total_seconds() / 3600 + 0.5
        occ = inside_now * surv(hours_from_now)
        for j, (tj, a) in enumerate(arrivals[: k + 1]):
            occ += a * surv((ts - tj).total_seconds() / 3600 + 0.5)
        share = occ / capacity
        level = "full" if share >= 0.9 else "busy" if share >= 0.7 else "comfortable"
        out.append({"hour_iso": ts.isoformat(), "predicted_inside": round(occ, 1),
                    "share": round(share, 3), "level": level})
    peak = max(out, key=lambda r: r["predicted_inside"]) if out else None
    alerts = [f"Expect about {int(r['predicted_inside'])} readers at {r['hour_iso'][11:16]} "
              f"({int(r['share'] * 100)}% of seats): {'open the overflow hall' if r['level'] == 'full' else 'add a desk assistant'}."
              for r in out if r["level"] != "comfortable"]
    return _clean({"capacity": capacity, "inside_now": inside_now, "model": fc["best"],
                   "median_stay_min": float(np.median(stays_h) * 60) if len(stays_h) else None,
                   "hours": out, "peak": peak, "alerts": alerts[:4]})
