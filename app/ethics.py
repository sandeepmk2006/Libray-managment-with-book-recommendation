"""Privacy, fairness and transparency audit.

- Pseudonymisation: salted SHA-256 member tokens, names dropped, timestamps coarsened
- k-anonymity check on quasi-identifiers before/after generalisation
- Consent: members who opt out never get personalised recommendations
- Fairness: recommendation quality parity across gender/department and
  disparate impact of a late-return risk model built *without* gender
"""
import hashlib
import os

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

SALT = os.environ.get("ATHENAEUM_SALT", "athenaeum-demo-salt")
QUASI = ["department", "year", "gender"]
SCHOOL = {"CSE": "Engineering", "AIDS": "Engineering", "ECE": "Engineering", "MECH": "Engineering",
          "BIOTECH": "Sciences", "MBA": "Management", "ENGLISH": "Humanities", "HISTORY": "Humanities",
          "FACULTY": "Faculty"}


def pseudonym(member_id):
    return "anon_" + hashlib.sha256((SALT + member_id).encode()).hexdigest()[:10]


def anonymised_sample(frames, n=8):
    v = frames["visits"].dropna(subset=["exit_time"]).sample(n, random_state=7)
    v = v.merge(frames["members"], on="member_id")
    return [{
        "token": pseudonym(r.member_id),
        "department": SCHOOL.get(r.department, "Other"),
        "cohort": "Faculty" if r.year == 0 else ("Junior" if r.year <= 2 else "Senior"),
        "entry_hour": r.entry_time.strftime("%a %H:00"),
        "stay_band": f"{int(r.duration_min // 30 * 30)}-{int(r.duration_min // 30 * 30 + 30)} min",
        "purpose": r.purpose or "Not recorded",
    } for r in v.itertuples()]


def k_anonymity(members, quasi, threshold=5):
    sizes = members.groupby(quasi).size()
    return {"quasi_identifiers": quasi, "k": int(sizes.min()),
            "groups": int(len(sizes)), "violations": int((sizes < threshold).sum()), "threshold": threshold}


def _late_model_parity(frames):
    loans = frames["loans"].dropna(subset=["returned"]).merge(frames["members"], on="member_id")
    loans = loans.merge(frames["books"][["book_id", "pages"]], on="book_id")
    loans = loans.sort_values("issued")
    loans["prior_loans"] = loans.groupby("member_id").cumcount()
    loans["prior_late"] = loans.groupby("member_id")["is_late"].transform(
        lambda s: s.astype(float).shift().expanding().mean()).fillna(0.35)
    X = loans[["year", "pages", "prior_loans", "prior_late"]].to_numpy(float)  # gender deliberately excluded
    y = loans["is_late"].astype(int).to_numpy()
    Xtr, Xte, ytr, yte, gtr, gte = train_test_split(X, y, loans["gender"].to_numpy(), test_size=0.3,
                                                     random_state=42, stratify=y)
    sc = StandardScaler().fit(Xtr)
    clf = LogisticRegression(max_iter=1000).fit(sc.transform(Xtr), ytr)
    pred = clf.predict(sc.transform(Xte))
    out = {}
    for g in sorted(set(gte)):
        m = gte == g
        tp = ((pred == 1) & (yte == 1) & m).sum()
        out[g] = {"n": int(m.sum()),
                  "favourable_rate": round(float((pred[m] == 0).mean()), 4),  # predicted on-time
                  "true_positive_rate": round(float(tp / max(1, ((yte == 1) & m).sum())), 4),
                  "accuracy": round(float((pred[m] == yte[m]).mean()), 4)}
    rates = [v["favourable_rate"] for v in out.values()]
    return out, round(min(rates) / max(rates), 4) if max(rates) else None


def _recommendation_parity(frames, recommender, sample=120):
    """Share of top-10 recommendations that fall in genres the member actually reads."""
    members = frames["members"]
    members = members[members.member_id.isin(recommender.uidx) & members.consent.astype(bool)]
    members = members.sample(min(sample, len(members)), random_state=1)
    genre_of = dict(zip(frames["books"].book_id, frames["books"].genre))
    read = frames["loans"].groupby("member_id")["book_id"].apply(lambda s: {genre_of[b] for b in s})
    rows = []
    for m in members.itertuples():
        recs = recommender.recommend(m.member_id, "hybrid", 10)["items"]
        match = np.mean([r["book"]["genre"] in read.get(m.member_id, set()) for r in recs]) if recs else 0
        rows.append({"gender": m.gender, "department": m.department, "match": match,
                     "score": np.mean([r["score"] for r in recs]) if recs else 0})
    df = pd.DataFrame(rows)
    agg = lambda col: {k: {"relevance": round(float(g["match"].mean()), 4), "n": int(len(g))}
                       for k, g in df.groupby(col)}
    return agg("gender"), agg("department")


def report(frames, recommender):
    members = frames["members"]
    generalised = members.assign(year=np.where(members.year == 0, "Faculty",
                                               np.where(members.year <= 2, "Junior", "Senior")),
                                 department=members.department.map(SCHOOL))
    # suppression: mask gender only for records still in groups smaller than the threshold
    small = generalised.groupby(QUASI)["member_id"].transform("size") < 5
    generalised.loc[small, "gender"] = "*"
    by_gender, by_dept = _recommendation_parity(frames, recommender)
    parity, di = _late_model_parity(frames)
    opted_in = int(members.consent.sum())
    return {
        "anonymised_sample": anonymised_sample(frames),
        "k_anonymity": {
            **k_anonymity(members, QUASI),
            "after_generalisation": {**k_anonymity(generalised, QUASI), "suppressed": int(small.sum())},
            "note": "Before any data leaves the system, year of study becomes Junior/Senior/Faculty and department becomes its school (Engineering, Sciences, Management, Humanities); records still in groups below the threshold have gender suppressed.",
        },
        "consent": {"opted_in": opted_in, "opted_out": int(len(members) - opted_in)},
        "fairness": {
            "recommendation_exposure_by_gender": by_gender,
            "by_department": by_dept,
            "late_model_parity": parity,
            "disparate_impact": di,
            "disparate_impact_rule": "Ratio of favourable outcome rates between groups; >= 0.8 passes the four-fifths rule.",
        },
        "transparency": [
            "Member IDs are replaced by salted SHA-256 pseudonyms in every export and analysis sample.",
            "Gender is stored only for fairness audits and is never used as a model feature.",
            f"{len(members) - opted_in} members opted out of personalisation and receive only non-personalised popular picks.",
            "Every recommendation carries human-readable reasons (the book it is anchored on, similar readers, ratings).",
            "Late-return risk predictions show the top contributing factors, never just a score.",
            "Gate logs record entry/exit time and an optional purpose only; no location tracking inside the library.",
            "Models are evaluated on held-out data and the metrics are published on the scorecard.",
        ],
    }
