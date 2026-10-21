"""Book recommendation engine.

Methods
-------
popular  : Bayesian-average rating x borrow volume (non-personalised baseline)
content  : TF-IDF over title/author/genre/description, user profile = rating-weighted
           centroid of what they read, ranked by cosine similarity
user_cf  : user-user collaborative filtering (mean-centred cosine, k nearest neighbours)
item_cf  : item-item collaborative filtering (adjusted cosine)
svd      : latent-factor matrix factorisation with biases trained by SGD (Funk SVD)
hybrid   : weighted blend of normalised scores + MMR re-ranking for diversity,
           with a cold-start fallback for members with no history

Interactions: explicit ratings (1-5); a borrow without a rating counts as an
implicit 3.5. Members who opted out of personalisation get `popular` only.
"""
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

IMPLICIT_RATING = 3.5
HYBRID_WEIGHTS = {"content": 0.55, "item_cf": 0.15, "user_cf": 0.15, "svd": 0.05, "popular": 0.10}  # tuned on hold-out NDCG
METHODS = ["hybrid", "content", "user_cf", "item_cf", "svd", "popular"]


def interactions_from(frames):
    """One row per (member, book) with an explicit or implicit rating."""
    r = frames["ratings"][["member_id", "book_id", "rating"]]
    l = frames["loans"][["member_id", "book_id"]].drop_duplicates()
    l = l.assign(rating=IMPLICIT_RATING)
    both = pd.concat([r, l]).drop_duplicates(["member_id", "book_id"], keep="first")
    return both.reset_index(drop=True)


def _minmax(x):
    x = np.asarray(x, float)
    lo, hi = np.nanmin(x), np.nanmax(x)
    return np.zeros_like(x) if hi - lo < 1e-12 else (x - lo) / (hi - lo)


class Recommender:
    def __init__(self, books, members, interactions, n_factors=12, epochs=60, seed=42):
        self.books = books.reset_index(drop=True)
        self.members = members.set_index("member_id")
        self.book_ids = self.books["book_id"].to_numpy()
        self.bidx = {b: i for i, b in enumerate(self.book_ids)}
        self.users = sorted(interactions["member_id"].unique())
        self.uidx = {u: i for i, u in enumerate(self.users)}
        nu, nb = len(self.users), len(self.book_ids)

        self.R = np.zeros((nu, nb))
        for m, b, r in interactions[["member_id", "book_id", "rating"]].itertuples(index=False):
            if b in self.bidx:
                self.R[self.uidx[m], self.bidx[b]] = r
        self.mask = self.R > 0
        cnt = self.mask.sum(1)
        self.user_mean = np.divide(self.R.sum(1), cnt, out=np.full(nu, 3.0), where=cnt > 0)
        self.global_mean = self.R[self.mask].mean() if self.mask.any() else 3.0

        self._fit_content()
        self._fit_cf()
        self._fit_svd(n_factors, epochs, seed)
        self._fit_popular()
        self._fit_dept_taste(interactions)

    # ---------------- training ----------------
    def _fit_content(self):
        b = self.books
        doc = (b["title"] + " " + b["author"] + " " + (b["genre"] + " ") * 3 + b["description"].fillna(""))
        self.tfidf = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=1, sublinear_tf=True)
        self.X = self.tfidf.fit_transform(doc)
        self.item_content_sim = cosine_similarity(self.X)

    def _fit_cf(self):
        centred = np.where(self.mask, self.R - self.user_mean[:, None], 0.0)
        self.centred = centred
        self.user_sim = cosine_similarity(centred)
        np.fill_diagonal(self.user_sim, 0)
        # adjusted cosine between items
        self.item_sim = cosine_similarity(centred.T)
        np.fill_diagonal(self.item_sim, 0)

    def _fit_svd(self, k, epochs, seed, lr=0.01, reg=0.05):
        rng = np.random.default_rng(seed)
        nu, nb = self.R.shape
        self.P = rng.normal(0, 0.1, (nu, k))
        self.Q = rng.normal(0, 0.1, (nb, k))
        self.bu = np.zeros(nu)
        self.bi = np.zeros(nb)
        us, its = np.nonzero(self.mask)
        rs = self.R[us, its]
        for _ in range(epochs):
            for j in rng.permutation(len(rs)):
                u, i = us[j], its[j]
                err = rs[j] - (self.global_mean + self.bu[u] + self.bi[i] + self.P[u] @ self.Q[i])
                self.bu[u] += lr * (err - reg * self.bu[u])
                self.bi[i] += lr * (err - reg * self.bi[i])
                pu = self.P[u].copy()
                self.P[u] += lr * (err * self.Q[i] - reg * pu)
                self.Q[i] += lr * (err * pu - reg * self.Q[i])

    def _fit_popular(self, m=5):
        n = self.mask.sum(0)
        s = self.R.sum(0)
        bayes = (s + m * self.global_mean) / (n + m)  # Bayesian average
        self.pop_score = _minmax(bayes) * 0.6 + _minmax(np.log1p(n)) * 0.4
        self.n_ratings = n

    def _fit_dept_taste(self, interactions):
        """Per-department borrowing profile, used for cold-start members."""
        df = interactions.merge(self.members[["department"]], left_on="member_id", right_index=True)
        self.dept_scores = {}
        for dept, g in df.groupby("department"):
            v = np.zeros(len(self.book_ids))
            for b, c in g["book_id"].value_counts().items():
                if b in self.bidx:
                    v[self.bidx[b]] = c
            self.dept_scores[dept] = _minmax(np.log1p(v))

    # ---------------- per-method scoring (full catalogue vector) ----------------
    def predict_rating(self, method, u, i):
        """Rating prediction used for RMSE; u,i are matrix indices."""
        if method == "svd":
            return float(np.clip(self.global_mean + self.bu[u] + self.bi[i] + self.P[u] @ self.Q[i], 1, 5))
        if method == "user_cf":
            sims = self.user_sim[u]
            raters = np.nonzero(self.mask[:, i])[0]
            top = raters[np.argsort(-sims[raters])[:25]]
            w = sims[top]
            if np.abs(w).sum() < 1e-9:
                return float(self.user_mean[u])
            return float(np.clip(self.user_mean[u] + w @ self.centred[top, i] / np.abs(w).sum(), 1, 5))
        if method == "item_cf":
            rated = np.nonzero(self.mask[u])[0]
            w = self.item_sim[i, rated]
            if np.abs(w).sum() < 1e-9:
                return float(self.user_mean[u])
            return float(np.clip(self.user_mean[u] + w @ self.centred[u, rated] / np.abs(w).sum(), 1, 5))
        return None

    def scores(self, method, u):
        if method == "popular":
            return self.pop_score.copy()
        if method == "content":
            rated = np.nonzero(self.mask[u])[0]
            weights = self.R[u, rated] - self.user_mean[u] + 0.5  # liked > disliked
            profile = (self.item_content_sim[rated] * weights[:, None]).sum(0)
            return _minmax(profile)
        if method == "user_cf":
            sims = self.user_sim[u]
            nn = np.argsort(-sims)[:30]
            s = sims[nn] @ self.centred[nn] / (np.abs(sims[nn]).sum() + 1e-9)
            return _minmax(s)
        if method == "item_cf":
            return _minmax(self.centred[u] @ self.item_sim + self.R[u] @ np.maximum(self.item_sim, 0) * 0.1)
        if method == "svd":
            return _minmax(self.bi + self.P[u] @ self.Q.T)
        if method == "hybrid":
            return sum(w * self.scores(m, u) for m, w in HYBRID_WEIGHTS.items())
        raise ValueError(f"unknown method {method}")

    # ---------------- public API ----------------
    def recommend(self, member_id, method="hybrid", k=10, exclude=None, diversify=True):
        exclude = set(exclude or [])
        member = self.members.loc[member_id] if member_id in self.members.index else None
        if member is not None and not int(member["consent"]):
            method = "popular"
        cold = member_id not in self.uidx
        if cold:
            dept = member["department"] if member is not None else None
            base = self.dept_scores.get(dept, np.zeros(len(self.book_ids)))
            s = 0.6 * base + 0.4 * self.pop_score
            seen = np.zeros(len(self.book_ids), bool)
            u = None
        else:
            u = self.uidx[member_id]
            s = self.scores(method, u)
            seen = self.mask[u].copy()
        for b in exclude:
            if b in self.bidx:
                seen[self.bidx[b]] = True
        s = np.where(seen, -np.inf, s)

        if diversify and method == "hybrid":
            order = self._mmr(s, k)
        else:
            order = [i for i in np.argsort(-s) if np.isfinite(s[i])][:k]
        top = s[order] if len(order) else np.array([])
        norm = _minmax(top) * 0.5 + 0.5 if len(top) > 1 else np.ones(len(top))
        items = [{
            "book": self._book(i),
            "score": round(float(norm[j]), 4),
            "reasons": self._reasons(u, i, method, member, cold),
        } for j, i in enumerate(order)]
        return {"member_id": member_id, "method": method, "cold_start": cold, "items": items}

    def _mmr(self, s, k, lam=0.9):
        """Maximal Marginal Relevance: trade relevance for genre/content diversity."""
        cand = [i for i in np.argsort(-s)[: k * 4] if np.isfinite(s[i])]
        rel = dict(zip(cand, _minmax(s[cand])))
        chosen = []
        while cand and len(chosen) < k:
            best = max(cand, key=lambda i: lam * rel[i] - (1 - lam) * max(
                (self.item_content_sim[i, j] for j in chosen), default=0))
            chosen.append(best)
            cand.remove(best)
        return chosen

    def similar(self, book_id, k=8):
        i = self.bidx[book_id]
        s = 0.75 * _minmax(self.item_content_sim[i]) + 0.25 * _minmax(self.item_sim[i])
        s[i] = -np.inf
        order = np.argsort(-s)[:k]
        out = []
        for j in order:
            reasons = []
            if self.books.genre[j] == self.books.genre[i]:
                reasons.append(f"Also {self.books.genre[j]}")
            if self.books.author[j] == self.books.author[i]:
                reasons.append(f"Same author: {self.books.author[j]}")
            co = int((self.mask[:, i] & self.mask[:, j]).sum())
            if co:
                reasons.append(f"{co} reader{'s' if co > 1 else ''} borrowed both")
            terms = self._shared_terms(i, j)
            if terms:
                reasons.append("Themes: " + ", ".join(terms))
            out.append({"book": self._book(j), "score": round(float(s[j]), 4), "reasons": reasons or ["Similar content"]})
        return {"items": out}

    # ---------------- explanations ----------------
    def _book(self, i):
        b = self.books.iloc[i]
        return {"book_id": int(b.book_id), "title": b.title, "author": b.author, "genre": b.genre, "year": int(b.year)}

    def _shared_terms(self, i, j, n=3):
        vocab = self.tfidf.get_feature_names_out()
        a, b = self.X[i].toarray()[0], self.X[j].toarray()[0]
        both = a * b
        genre_words = {w for g in self.books.genre.unique() for w in g.lower().split()}
        idx = [t for t in np.argsort(-both)[:n * 4] if both[t] > 0 and not set(vocab[t].split()) & genre_words]
        return [vocab[t] for t in idx[:n]]

    def _reasons(self, u, i, method, member, cold):
        reasons = []
        genre = self.books.genre[i]
        if cold:
            if member is not None:
                reasons.append(f"Popular with {member['department']} readers")
            reasons.append("New reader: starting with crowd favourites")
            return reasons
        rated = np.nonzero(self.mask[u])[0]
        if len(rated):
            liked = rated[self.R[u, rated] >= max(3.5, self.user_mean[u])]
            pool = liked if len(liked) else rated
            anchor = pool[np.argmax(self.item_content_sim[i, pool] + 0.3 * self.item_sim[i, pool])]
            reasons.append(f"Because you read “{self.books.title[anchor]}”")
            g_share = (self.books.genre.to_numpy()[rated] == genre).mean()
            if g_share >= 0.2:
                reasons.append(f"You often read {genre}")
        if method in ("user_cf", "hybrid"):
            nn = np.argsort(-self.user_sim[u])[:30]
            fans = nn[self.R[nn, i] >= 4]
            if len(fans):
                reasons.append(f"{len(fans)} reader{'s' if len(fans) > 1 else ''} like you loved it")
        if method in ("svd", "hybrid") and self.n_ratings[i] >= 5:
            reasons.append(f"Rated {self.R[self.mask[:, i], i].mean():.1f}★ by {int(self.n_ratings[i])} readers")
        if method == "popular" or not reasons:
            reasons.append("Trending in the library")
        return reasons[:3]


# ---------------- evaluation (Module 5: evaluating recommenders) ----------------
def evaluate(frames, k=10, test_frac=0.2, seed=42, min_items=5):
    """Per-user random hold-out. Ranking metrics count held-out books the user
    rated >= 3.5 (or borrowed) as relevant; RMSE on held-out explicit ratings."""
    rng = np.random.default_rng(seed)
    inter = interactions_from(frames)
    train_parts, test_parts = [], []
    for _, g in inter.groupby("member_id"):
        if len(g) < min_items:
            train_parts.append(g)
            continue
        idx = rng.permutation(len(g))
        n_test = max(1, int(len(g) * test_frac))
        test_parts.append(g.iloc[idx[:n_test]])
        train_parts.append(g.iloc[idx[n_test:]])
    train, test = pd.concat(train_parts), pd.concat(test_parts)
    rec = Recommender(frames["books"], frames["members"], train)
    explicit = test.merge(frames["ratings"][["member_id", "book_id"]], on=["member_id", "book_id"])

    results = {}
    for method in METHODS:
        prec, recall, ndcg, hits, recommended, ild = [], [], [], [], set(), []
        for m, g in test.groupby("member_id"):
            if m not in rec.uidx:
                continue
            relevant = set(g.loc[g.rating >= 3.5, "book_id"])
            if not relevant:
                continue
            s = rec.scores(method, rec.uidx[m])
            s = np.where(rec.mask[rec.uidx[m]], -np.inf, s)
            order = rec._mmr(s, k) if method == "hybrid" else list(np.argsort(-s)[:k])
            top = [int(rec.book_ids[i]) for i in order]
            recommended.update(top)
            hit = [b in relevant for b in top]
            prec.append(sum(hit) / k)
            recall.append(sum(hit) / len(relevant))
            hits.append(float(any(hit)))
            dcg = sum(h / np.log2(r + 2) for r, h in enumerate(hit))
            idcg = sum(1 / np.log2(r + 2) for r in range(min(len(relevant), k)))
            ndcg.append(dcg / idcg)
            sims = rec.item_content_sim[np.ix_(order, order)]
            ild.append(1 - sims[np.triu_indices(len(order), 1)].mean())
        rmse = None
        if method in ("svd", "user_cf", "item_cf"):
            errs = [(rec.predict_rating(method, rec.uidx[m], rec.bidx[b]) - r) ** 2
                    for m, b, r in explicit[["member_id", "book_id", "rating"]].itertuples(index=False)
                    if m in rec.uidx and b in rec.bidx]
            rmse = round(float(np.sqrt(np.mean(errs))), 4) if errs else None
        results[method] = {
            "precision": round(float(np.mean(prec)), 4), "recall": round(float(np.mean(recall)), 4),
            "ndcg": round(float(np.mean(ndcg)), 4), "hit_rate": round(float(np.mean(hits)), 4),
            "coverage": round(len(recommended) / len(rec.book_ids), 4),
            "diversity": round(float(np.mean(ild)), 4), "rmse": rmse,
        }
    return {"k": k, "methods": results, "users_evaluated": int(test.member_id.nunique()),
            "protocol": f"Per-member random {int(test_frac * 100)}% hold-out (members with >= {min_items} books); "
                        f"relevant = held-out books rated >= 3.5 or borrowed; models retrained on the training split only."}
