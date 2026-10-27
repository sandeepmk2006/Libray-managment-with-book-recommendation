"""Web scraper: builds the book catalogue from Open Library (openlibrary.org).

Pipeline
  1. For each genre, query the Open Library search API by subject, sorted by
     reading-log activity (how many people logged the book).
  2. Keep real metadata: title, author, first publish year, median page count,
     community rating average/count, want-to-read and already-read counts, subjects.
  3. Visit each work page (/works/<id>.json) to scrape its description.
  4. Clean: drop duplicates, missing titles/authors, non-text noise; normalise
     whitespace; fill missing pages with the genre median.
  5. Save data/books_scraped.csv (+ a raw JSON snapshot for reproducibility).

Run:  python -m app.scraper  [--per-genre 30 --workers 6]
Be polite: identifies itself with a User-Agent, limits concurrency and retries with backoff.
"""
import argparse
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests

from .db import ROOT

API = "https://openlibrary.org"
HEADERS = {"User-Agent": "Athenaeum-student-project/1.0 (Data Science Ecosystem coursework)"}
FIELDS = ("key,title,author_name,language,first_publish_year,number_of_pages_median,ratings_average,"
          "ratings_count,want_to_read_count,already_read_count,currently_reading_count,subject")

# library genre -> Open Library subject slug(s). Order matters: a book listed under several
# subjects keeps the FIRST genre here, so narrow genres come before broad ones.
GENRES = {
    "Young Adult": ["young_adult_fiction"],
    "Graphic Novel": ["graphic_novels"],
    "Poetry": ["poetry"],
    "Horror": ["horror"],
    "Computer Science": ["computer_programming", "algorithms"],
    "Fantasy": ["fantasy"],
    "Science Fiction": ["science_fiction"],
    "Mystery": ["mystery_and_detective_stories"],
    "Romance": ["romance"],
    "Biography": ["autobiography"],
    "Psychology": ["psychology"],
    "Self Help": ["self-help"],
    "Economics": ["economics"],
    "Science": ["popular_science"],
    "Philosophy": ["philosophy", "ethics"],
    "History": ["world_history", "history", "military_history"],
    "Classics": ["classic_literature"],
    "Literary Fiction": ["literary_fiction"],
}
NON_FICTION = {"Computer Science", "Biography", "Psychology", "Self Help", "Economics", "Science",
               "Philosophy", "History"}
OUT_CSV = os.path.join(ROOT, "data", "books_scraped.csv")
OUT_RAW = os.path.join(ROOT, "data", "raw", "openlibrary_snapshot.json")


def _get(url, params=None, tries=4):
    for attempt in range(tries):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=30)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (429, 500, 502, 503):
                time.sleep(2 ** attempt)
                continue
            return None
        except requests.RequestException:
            time.sleep(2 ** attempt)
    return None


def search_genre(genre, subjects, n):
    docs = []
    for subject in subjects:
        data = _get(f"{API}/search.json", {"subject": subject, "sort": "readinglog", "limit": n * 3,
                                           "fields": FIELDS, "lang": "en"})
        docs.extend((data or {}).get("docs", []))
    for d in docs:
        d["genre"] = genre
    return docs


def _is_fiction(subjects):
    s = " ".join(subjects or []).lower()
    return "fiction" in s.replace("nonfiction", "").replace("non-fiction", "")


def _clean_text(s):
    if isinstance(s, dict):
        s = s.get("value", "")
    s = str(s or "")
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)     # markdown links -> text
    s = re.sub(r"https?://\S+", " ", s)                  # bare urls
    s = re.sub(r"-{3,}.*", " ", s, flags=re.S)           # "----" footers (source notes)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:900]


def work_description(key):
    data = _get(f"{API}{key}.json")
    return _clean_text((data or {}).get("description", ""))


def scrape(per_genre=30, workers=6, verbose=True):
    rows = []
    for genre, subject in GENRES.items():
        docs = search_genre(genre, subject, per_genre)
        if verbose:
            print(f"{genre:<18} {len(docs):>3} candidates")
        rows.extend(docs)
        time.sleep(0.5)
    raw = pd.DataFrame(rows)

    # ---- cleaning ----
    df = raw.dropna(subset=["title", "author_name"]).copy()
    df["author"] = df["author_name"].map(lambda a: a[0] if isinstance(a, list) and a else None)
    df = df.dropna(subset=["author"])
    # English editions only (drops translations such as "Manifest der Kommunistischen Partei")
    df = df[df["language"].map(lambda l: isinstance(l, list) and "eng" in l)]
    df = df[df["title"].str.match(r"^[ -~’]+$")]
    # subject tags are crowd-sourced: a novel tagged "computers" must not sit in a non-fiction genre
    df = df[~(df["genre"].isin(NON_FICTION) & df["subject"].map(_is_fiction))]
    df = df.drop_duplicates("key")                     # a work listed under two subjects keeps the first genre
    df["norm_title"] = df["title"].str.lower().str.replace(r"[^a-z0-9]", "", regex=True)
    df = df.drop_duplicates("norm_title")
    df = df.groupby("genre", group_keys=False).head(per_genre)

    if verbose:
        print(f"Fetching {len(df)} descriptions ...")
    with ThreadPoolExecutor(max_workers=workers) as ex:
        df["description"] = list(ex.map(work_description, df["key"]))

    subj = df["subject"].map(lambda s: [x for x in (s or []) if len(x) < 40][:12] if isinstance(s, list) else [])
    df["subjects"] = subj.map(lambda s: "; ".join(s))
    # books with no scraped description fall back to their subject tags as text
    empty = df["description"].str.len() < 40
    df.loc[empty, "description"] = df.loc[empty, "subjects"]
    df = df[df["description"].str.len() >= 20]

    df["pages"] = df["number_of_pages_median"]
    df["pages"] = df["pages"].fillna(df.groupby("genre")["pages"].transform("median")).fillna(250).astype(int)
    out = pd.DataFrame({
        "book_id": range(1, len(df) + 1),
        "title": df["title"].str.strip(),
        "author": df["author"].str.strip(),
        "genre": df["genre"],
        "year": df["first_publish_year"].fillna(0).astype(int),
        "pages": df["pages"],
        "description": df["description"],
        "ol_key": df["key"],
        "ol_rating": df["ratings_average"].round(2),
        "ol_rating_count": df["ratings_count"].fillna(0).astype(int),
        "want_to_read": df["want_to_read_count"].fillna(0).astype(int),
        "already_read": df["already_read_count"].fillna(0).astype(int),
        "subjects": df["subjects"],
    })
    os.makedirs(os.path.dirname(OUT_RAW), exist_ok=True)
    with open(OUT_RAW, "w", encoding="utf-8") as fh:
        json.dump({"scraped_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "source": API,
                   "records": raw.drop(columns=["subject", "language"], errors="ignore").to_dict("records")}, fh, default=str)
    out.to_csv(OUT_CSV, index=False)
    report = {
        "candidates": int(len(raw)), "kept": int(len(out)),
        "dropped_duplicates_or_missing": int(len(raw) - len(out)),
        "with_description": int((df["description"].str.len() >= 40).sum()),
        "with_rating": int(out["ol_rating"].notna().sum()),
    }
    if verbose:
        print(report)
    return out, report


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-genre", type=int, default=30)
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    scrape(a.per_genre, a.workers)
