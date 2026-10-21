"""Tests for app.analytics – verifies contract keys and JSON serialisability.

Seeds a small temp DB via app.seed.seed_database(path=tmp, n_members=80, days=40)
then checks each public function returns the expected top-level keys and that
json.dumps(..., allow_nan=False) succeeds (no NaN / Inf / numpy types).
"""
import json
import os
import tempfile

import pytest

from app.db import connect, load_frames
from app.seed import seed_database
from app import analytics as a


# ── Fixture: tiny seeded database ──────────────────────────────────────────

@pytest.fixture(scope="module")
def frames():
    """Create a small temporary database and return load_frames dict."""
    fd, tmp_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        seed_database(path=tmp_path, n_members=80, days=40, seed=42)
        conn = connect(tmp_path)
        f = load_frames(conn)
        yield f
        conn.close()
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


# ── Helpers ────────────────────────────────────────────────────────────────

def _json_ok(obj, label=""):
    """Assert json.dumps(obj, allow_nan=False) succeeds."""
    try:
        json.dumps(obj, allow_nan=False)
    except (ValueError, TypeError) as exc:
        pytest.fail(f"JSON serialisation failed for {label}: {exc}")


# ── EDA ────────────────────────────────────────────────────────────────────

def test_eda_keys(frames):
    r = a.eda(frames)
    _json_ok(r, "eda")
    expected = {"summary", "describe", "hourly", "weekday_hour", "daily",
                "by_department", "by_purpose", "genre_popularity", "top_books",
                "correlation", "stay_histogram", "outliers"}
    assert expected <= set(r.keys()), f"Missing EDA keys: {expected - set(r.keys())}"


def test_eda_describe_keys(frames):
    r = a.eda(frames)
    desc_keys = {"duration_min", "loans_per_member", "rating", "pages", "days_late"}
    assert desc_keys <= set(r["describe"].keys())
    stat_keys = {"count", "mean", "median", "std", "var", "min", "q1", "q3",
                 "max", "skew", "kurtosis"}
    for var in desc_keys:
        assert stat_keys <= set(r["describe"][var].keys()), \
            f"Missing stat keys in describe[{var}]"


def test_eda_hourly_length(frames):
    r = a.eda(frames)
    assert len(r["hourly"]) == 24


def test_eda_weekday_hour_shape(frames):
    r = a.eda(frames)
    assert len(r["weekday_hour"]) == 7
    for row in r["weekday_hour"]:
        assert len(row) == 24


def test_eda_correlation(frames):
    r = a.eda(frames)
    assert "columns" in r["correlation"]
    assert "matrix" in r["correlation"]
    n = len(r["correlation"]["columns"])
    assert len(r["correlation"]["matrix"]) == n


def test_eda_outliers(frames):
    r = a.eda(frames)
    assert r["outliers"]["method"] == "IQR"
    for k in ("lower", "upper", "count"):
        assert k in r["outliers"]


# ── Hypothesis ─────────────────────────────────────────────────────────────

def test_hypothesis_keys(frames):
    r = a.hypothesis(frames)
    _json_ok(r, "hypothesis")
    assert "tests" in r
    assert "confidence_intervals" in r
    assert len(r["tests"]) >= 6


def test_hypothesis_test_shape(frames):
    r = a.hypothesis(frames)
    required = {"name", "question", "h0", "h1", "test", "statistic", "p_value",
                "alpha", "decision", "interpretation", "effect_size"}
    for t in r["tests"]:
        assert required <= set(t.keys()), f"Missing keys in test '{t.get('name')}': {required - set(t.keys())}"
        assert t["decision"] in ("Reject H0", "Fail to reject H0")


def test_hypothesis_ci_shape(frames):
    r = a.hypothesis(frames)
    ci_keys = {"metric", "mean", "low", "high", "level"}
    for ci in r["confidence_intervals"]:
        assert ci_keys <= set(ci.keys())
        assert ci["level"] == 0.95


# ── Forecast ───────────────────────────────────────────────────────────────

def test_forecast_keys(frames):
    r = a.forecast(frames)
    _json_ok(r, "forecast")
    expected = {"target", "models", "best", "next_24h", "actual_vs_pred"}
    assert expected <= set(r.keys())
    assert r["target"] == "hourly footfall"


def test_forecast_models(frames):
    r = a.forecast(frames)
    names = {m["name"] for m in r["models"]}
    assert "Linear Regression" in names
    assert "Polynomial Regression" in names
    assert "Multiple Linear Regression" in names
    model_keys = {"name", "r2", "mae", "rmse", "coefficients"}
    for m in r["models"]:
        assert model_keys <= set(m.keys()), f"Missing keys in model '{m['name']}'"


def test_forecast_actual_vs_pred(frames):
    r = a.forecast(frames)
    assert len(r["actual_vs_pred"]) > 0
    avp_keys = {"x", "actual", "linear", "polynomial", "multiple"}
    for row in r["actual_vs_pred"]:
        assert avp_keys <= set(row.keys())


# ── Classify ───────────────────────────────────────────────────────────────

def test_classify_keys(frames):
    r = a.classify(frames)
    _json_ok(r, "classify")
    expected = {"target", "features", "class_balance", "models", "best",
                "feature_importance", "tree_rules", "roc"}
    assert expected <= set(r.keys())
    assert r["target"] == "late return"


def test_classify_models(frames):
    r = a.classify(frames)
    names = {m["name"] for m in r["models"]}
    for req in ("Logistic Regression", "KNN", "Decision Tree", "Random Forest"):
        assert req in names, f"Missing model: {req}"
    model_keys = {"name", "accuracy", "precision", "recall", "f1", "roc_auc",
                  "confusion", "cv_mean", "cv_std"}
    for m in r["models"]:
        assert model_keys <= set(m.keys())
        assert len(m["confusion"]) == 2
        assert len(m["confusion"][0]) == 2


def test_classify_class_balance(frames):
    r = a.classify(frames)
    assert "late" in r["class_balance"]
    assert "on_time" in r["class_balance"]


def test_classify_roc(frames):
    r = a.classify(frames)
    for name, curve in r["roc"].items():
        assert "fpr" in curve and "tpr" in curve
        assert len(curve["fpr"]) <= 50


# ── Predict Late ───────────────────────────────────────────────────────────

def test_predict_late(frames):
    mid = frames["members"]["member_id"].iloc[0]
    bid = int(frames["books"]["book_id"].iloc[0])
    r = a.predict_late(frames, mid, bid)
    _json_ok(r, "predict_late")
    assert "probability" in r
    assert "label" in r
    assert "top_factors" in r
    assert r["label"] in ("late", "on_time")
    assert 0 <= r["probability"] <= 1
    assert len(r["top_factors"]) <= 5


# ── Clusters ───────────────────────────────────────────────────────────────

def test_clusters_keys(frames):
    r = a.clusters(frames)
    _json_ok(r, "clusters")
    expected = {"features", "elbow", "chosen_k", "kmeans", "agglomerative"}
    assert expected <= set(r.keys())


def test_clusters_elbow(frames):
    r = a.clusters(frames)
    assert len(r["elbow"]) == 7  # k=2..8
    for e in r["elbow"]:
        assert {"k", "inertia", "silhouette"} <= set(e.keys())


def test_clusters_kmeans(frames):
    r = a.clusters(frames)
    km = r["kmeans"]
    assert "points" in km
    assert "centroids_profile" in km
    assert len(km["centroids_profile"]) == r["chosen_k"]
    for p in km["centroids_profile"]:
        assert "cluster" in p
        assert "size" in p
        assert "persona" in p


def test_clusters_agglomerative(frames):
    r = a.clusters(frames)
    ag = r["agglomerative"]
    assert "silhouette" in ag
    assert "agreement_ari" in ag
    assert "dendrogram" in ag
    dend = ag["dendrogram"]
    assert "icoord" in dend
    assert "dcoord" in dend
    assert "labels" in dend
