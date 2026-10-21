"""Synthetic but behaviour-driven data generator.

Each member gets a latent taste vector (department prior + personal noise).
Visits, loans, ratings and late returns are all *derived* from latent traits,
so the analytics and ML modules have real signal to discover.

Run:  python -m app.seed  [--members 320 --days 120 --seed 42]
"""
import argparse
import os
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from .db import DB_PATH, ROOT, connect, init_schema

DEPARTMENTS = {
    # department: (share, genre affinity boosts)
    "CSE":     (0.24, {"Computer Science": 2.2, "Science Fiction": 1.4, "Self Help": 0.6, "Economics": 0.4}),
    "AIDS":    (0.12, {"Computer Science": 2.4, "Science": 0.9, "Psychology": 0.6, "Science Fiction": 0.8}),
    "ECE":     (0.13, {"Science": 1.4, "Computer Science": 1.2, "Science Fiction": 1.0, "Biography": 0.6}),
    "MECH":    (0.10, {"Biography": 1.3, "Science": 0.9, "Self Help": 1.0, "Young Adult": 0.5}),
    "BIOTECH": (0.09, {"Science": 2.0, "History": 0.6, "Psychology": 0.8, "Mystery": 0.5}),
    "MBA":     (0.10, {"Economics": 2.4, "Self Help": 1.6, "Psychology": 1.2, "Biography": 1.0}),
    "ENGLISH": (0.11, {"Classics": 2.2, "Literary Fiction": 2.0, "Poetry": 1.6, "Romance": 0.9, "Philosophy": 0.8}),
    "HISTORY": (0.06, {"History": 2.4, "Philosophy": 1.4, "Biography": 1.0, "Classics": 0.8, "Graphic Novel": 0.6}),
    "FACULTY": (0.05, {"History": 1.0, "Science": 1.0, "Philosophy": 1.0, "Computer Science": 1.0, "Classics": 0.8}),
}
PURPOSES = ["Study", "Borrow/Return", "Research", "Group Discussion", "Reading", "Exam Prep"]
FIRST = ["Aarav", "Diya", "Vihaan", "Ananya", "Arjun", "Ishita", "Sai", "Meera", "Rohan", "Kavya",
         "Aditya", "Nila", "Karthik", "Sneha", "Rahul", "Priya", "Joel", "Fathima", "Nikhil", "Riya",
         "Varun", "Aishwarya", "Abhinav", "Lakshmi", "Dev", "Sana", "Harish", "Tanvi", "Manoj", "Divya",
         "Akash", "Pooja", "Sanjay", "Neha", "Ashwin", "Keerthana", "Gokul", "Swathi", "Pranav", "Anjali"]
LAST = ["Kumar", "Sharma", "Nair", "Reddy", "Iyer", "Menon", "Das", "Patel", "Joseph", "Thomas",
        "Raj", "Pillai", "Singh", "Krishnan", "Varma", "George", "Rao", "Mathew", "Prakash", "Shetty"]
FEMALE = {"Diya", "Ananya", "Ishita", "Meera", "Kavya", "Nila", "Sneha", "Priya", "Fathima", "Riya",
          "Aishwarya", "Lakshmi", "Sana", "Tanvi", "Divya", "Pooja", "Neha", "Keerthana", "Swathi", "Anjali"}

# relative arrival intensity per hour (library open 8:00-21:00)
HOURLY = np.array([0, 0, 0, 0, 0, 0, 0, 0, 1.2, 2.4, 3.0, 3.6, 2.2, 2.6, 3.4, 3.8, 3.0, 2.2, 1.6, 1.0, 0.6, 0])
WEEKDAY = np.array([1.0, 1.05, 1.0, 1.1, 0.9, 0.55, 0.3])  # Mon..Sun


def _softmax(x):
    e = np.exp(x - x.max())
    return e / e.sum()


def generate(n_members=320, days=120, seed=42, now=None):
    rng = np.random.default_rng(seed)
    now = (now or datetime.now()).replace(second=0, microsecond=0)
    start = (now - timedelta(days=days)).replace(hour=0, minute=0)

    books = pd.read_csv(os.path.join(ROOT, "data", "books.csv"))
    books["copies"] = rng.integers(2, 6, len(books))
    genres = sorted(books["genre"].unique())
    g_idx = {g: i for i, g in enumerate(genres)}
    popularity = rng.lognormal(0, 0.6, len(books))  # some books are simply more popular

    # ---------------- members with latent traits ----------------
    dept_names = list(DEPARTMENTS)
    shares = np.array([DEPARTMENTS[d][0] for d in dept_names]); shares /= shares.sum()
    members, traits = [], []
    for i in range(n_members):
        dept = rng.choice(dept_names, p=shares)
        first = rng.choice(FIRST)
        taste = rng.normal(0, 0.7, len(genres))
        for g, boost in DEPARTMENTS[dept][1].items():
            taste[g_idx[g]] += boost
        year = 0 if dept == "FACULTY" else int(rng.integers(1, 5))
        members.append({
            "member_id": f"KU{24000 + i:05d}",
            "name": f"{first} {rng.choice(LAST)}",
            "department": dept,
            "year": year,
            "gender": "F" if first in FEMALE else "M",
            "joined": (start - timedelta(days=int(rng.integers(30, 900)))).date().isoformat(),
            "consent": int(rng.random() > 0.06),
        })
        traits.append({
            "taste": taste,
            "diligence": float(np.clip(rng.normal(0.6 if year != 1 else 0.45, 0.2), 0.02, 1)),
            "visit_rate": float(rng.gamma(2.0, 0.22)),        # visits/day
            "stay_mu": float(rng.normal(np.log(75), 0.35)),   # lognormal mean of stay
            "reader": float(rng.gamma(2.2, 0.85)),             # borrowing appetite
            "early_bird": float(rng.normal(0, 1.5)),          # shifts preferred hour
        })

    # ---------------- visits ----------------
    visits = []
    exam_days = {start.date() + timedelta(days=d) for d in range(days - 25, days - 12)}
    for m, t in zip(members, traits):
        for d in range(days + 1):
            day = start + timedelta(days=d)
            if day > now:
                break
            rate = t["visit_rate"] * WEEKDAY[day.weekday()] * (1.8 if day.date() in exam_days else 1)
            for _ in range(rng.poisson(rate)):
                hour_p = HOURLY * np.exp(-((np.arange(22) - (13 + t["early_bird"])) ** 2) / 60)
                hour = rng.choice(22, p=hour_p / hour_p.sum())
                entry = day + timedelta(hours=int(hour), minutes=int(rng.integers(0, 60)))
                stay = float(np.clip(rng.lognormal(t["stay_mu"] + (0.35 if day.date() in exam_days else 0), 0.45), 6, 420))
                exit_ = entry + timedelta(minutes=stay)
                close = day.replace(hour=21, minute=0)
                exit_ = min(exit_, close)
                if entry >= now:
                    continue
                purpose = rng.choice(PURPOSES, p=[.32, .2, .12, .1, .16, .1])
                if day.date() in exam_days and rng.random() < .4:
                    purpose = "Exam Prep"
                visits.append({
                    "member_id": m["member_id"],
                    "entry_time": entry.isoformat(timespec="seconds"),
                    "exit_time": None if exit_ > now else exit_.isoformat(timespec="seconds"),
                    "purpose": None if rng.random() < 0.07 else purpose,
                })
    # make sure the "live" gate view is never empty during opening hours
    visits_df = pd.DataFrame(visits)

    # ---------------- loans + ratings ----------------
    loans, ratings = [], {}
    genre_of = books["genre"].map(g_idx).to_numpy()
    for m, t in zip(members, traits):
        n_loans = rng.poisson(t["reader"] * days / 30)
        if n_loans == 0:
            continue
        logits = t["taste"][genre_of] * 1.3 + np.log(popularity)
        p = _softmax(logits)
        chosen = rng.choice(len(books), size=min(n_loans, len(books) // 2), replace=False, p=p)
        for bi in chosen:
            issued = start + timedelta(days=float(rng.uniform(0, days)), hours=float(rng.uniform(9, 18)))
            if issued > now:
                continue
            due = issued + timedelta(days=14)
            late_p = 1 / (1 + np.exp(-(-1.3 - 3.2 * (t["diligence"] - 0.5) + books.pages[bi] / 600
                                       + (0.4 if m["year"] == 1 else 0) + (0.3 if n_loans > 8 else 0))))
            if rng.random() < late_p:
                ret = due + timedelta(days=float(rng.gamma(1.6, 3.5)))
            else:
                ret = issued + timedelta(days=float(rng.uniform(2, 14)))
            loans.append({
                "member_id": m["member_id"], "book_id": int(books.book_id[bi]),
                "issued": issued.isoformat(timespec="seconds"), "due": due.isoformat(timespec="seconds"),
                "returned": None if ret > now else ret.isoformat(timespec="seconds"),
            })
            if ret <= now and rng.random() < 0.85:
                aff = t["taste"][genre_of[bi]]
                r = 2.5 + 0.8 * aff + 0.25 * np.log(popularity[bi]) + rng.normal(0, 0.6)
                ratings[(m["member_id"], int(books.book_id[bi]))] = {
                    "member_id": m["member_id"], "book_id": int(books.book_id[bi]),
                    "rating": float(np.clip(np.round(r * 2) / 2, 1, 5)),
                    "ts": ret.isoformat(timespec="seconds"),
                }
    return (pd.DataFrame(members), books, visits_df, pd.DataFrame(loans), pd.DataFrame(list(ratings.values())))


def seed_database(path=None, **kw):
    path = path or DB_PATH
    if os.path.exists(path):
        os.remove(path)
    members, books, visits, loans, ratings = generate(**kw)
    conn = connect(path)
    init_schema(conn)
    for name, df in [("members", members), ("books", books), ("visits", visits),
                     ("loans", loans), ("ratings", ratings)]:
        df.to_sql(name, conn, if_exists="append", index=False)
    conn.commit()
    counts = {n: conn.execute(f"SELECT COUNT(*) FROM {n}").fetchone()[0]
              for n in ("members", "books", "visits", "loans", "ratings")}
    conn.close()
    return counts


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--members", type=int, default=320)
    ap.add_argument("--days", type=int, default=120)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    print(seed_database(n_members=a.members, days=a.days, seed=a.seed))
