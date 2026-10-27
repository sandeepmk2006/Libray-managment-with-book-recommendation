"""Flask application: REST API (docs/API_CONTRACT.md) + static SPA."""
import os
import random
import threading
from datetime import datetime, timedelta

import numpy as np
from flask import Flask, Response, jsonify, request, send_from_directory

from . import ethics, graph
from .db import DB_PATH, connect, init_schema, load_frames
from .recommender import METHODS, Recommender, evaluate, interactions_from

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
CAPACITY = 60   # reading-room seats


class State:
    """Data version counter + memoised frames/models, rebuilt lazily after writes."""

    def __init__(self, path):
        self.conn = connect(path)
        init_schema(self.conn)
        self.lock = threading.RLock()
        self.version = 0
        self.cache = {}

    def bump(self):
        with self.lock:
            self.version += 1

    def memo(self, key, fn, ttl_versions=0):
        """Cache fn() until the data version moves more than ttl_versions past it."""
        with self.lock:
            hit = self.cache.get(key)
            if hit and self.version - hit[0] <= ttl_versions:
                return hit[1]
            val = fn()
            self.cache[key] = (self.version, val)
            return val

    def frames(self):
        return self.memo("frames", lambda: load_frames(self.conn))

    def recommender(self):
        def build():
            f = self.frames()
            return Recommender(f["books"], f["members"], interactions_from(f), f["visits"])
        return self.memo("rec", build, ttl_versions=200)  # gate scans bump the version too; retrain after many writes


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def clean(o):
    """Make numpy/pandas values JSON-safe."""
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else round(float(o), 4)
    if hasattr(o, "isoformat"):
        return o.isoformat()
    return o


def create_app(db_path=None):
    db_path = db_path or DB_PATH
    if not os.path.exists(db_path):
        from .seed import seed_database
        seed_database(db_path)
    app = Flask(__name__, static_folder=None)
    st = State(db_path)
    app.config["STATE"] = st
    q = lambda sql, *a: [dict(r) for r in st.conn.execute(sql, a).fetchall()]
    ok = lambda o: jsonify(clean(o))
    err = lambda msg, code=400: (jsonify({"error": msg}), code)

    # warm the models in the background so the first page loads quickly
    def _warm():
        from . import analytics
        st.recommender()
        st.memo("rec_eval", lambda: evaluate(st.frames()), ttl_versions=10**9)
        for name in ("eda", "forecast", "hypothesis", "classify", "clusters"):
            st.memo(f"an_{name}", lambda n=name: getattr(analytics, n)(st.frames()), ttl_versions=50)
    if not app.testing and os.environ.get("ATHENAEUM_NO_WARMUP") != "1":
        threading.Thread(target=_warm, daemon=True).start()

    # one shared SQLite connection: serialise API requests touching it
    @app.before_request
    def _lock():
        if request.path.startswith("/api/"):
            st.lock.acquire()

    @app.teardown_request
    def _unlock(_exc):
        if request.path.startswith("/api/"):
            st.lock.release()

    # ---------------- static SPA ----------------
    @app.get("/")
    def index():
        return send_from_directory(STATIC, "index.html")

    @app.get("/<path:p>")
    def static_files(p):
        if p.startswith("api/"):
            return err("not found", 404)
        full = os.path.join(STATIC, p)
        return send_from_directory(STATIC, p) if os.path.isfile(full) else send_from_directory(STATIC, "index.html")

    # ---------------- overview ----------------
    @app.get("/api/overview")
    def overview():
        today = datetime.now().date().isoformat()
        hourly = [0] * 24
        for r in q("SELECT CAST(substr(entry_time,12,2) AS INT) h, COUNT(*) c FROM visits "
                   "WHERE substr(entry_time,1,10)=? GROUP BY h", today):
            hourly[r["h"]] = r["c"]
        busiest = q("SELECT CAST(substr(entry_time,12,2) AS INT) h, COUNT(*) c FROM visits GROUP BY h ORDER BY c DESC LIMIT 1")
        stay = q("SELECT AVG((julianday(exit_time)-julianday(entry_time))*1440) m FROM visits "
                 "WHERE exit_time IS NOT NULL AND entry_time >= ?", (datetime.now() - timedelta(days=30)).isoformat())
        one = lambda sql, *a: st.conn.execute(sql, a).fetchone()[0]
        return ok({
            "inside_now": one("SELECT COUNT(*) FROM visits WHERE exit_time IS NULL"),
            "visits_today": sum(hourly),
            "total_members": one("SELECT COUNT(*) FROM members"),
            "total_books": one("SELECT COUNT(*) FROM books"),
            "active_loans": one("SELECT COUNT(*) FROM loans WHERE returned IS NULL"),
            "overdue_loans": one("SELECT COUNT(*) FROM loans WHERE returned IS NULL AND due < ?", now_iso()),
            "avg_stay_min": stay[0]["m"],
            "busiest_hour": busiest[0]["h"] if busiest else None,
            "today_hourly": hourly,
            "capacity": CAPACITY,
        })

    # ---------------- gate ----------------
    def scan(member_id, purpose=None):
        member = q("SELECT member_id,name,department,year FROM members WHERE member_id=?", member_id)
        if not member:
            return None
        member, t = member[0], now_iso()
        open_visit = q("SELECT visit_id, entry_time FROM visits WHERE member_id=? AND exit_time IS NULL", member_id)
        if open_visit:
            v = open_visit[0]
            st.conn.execute("UPDATE visits SET exit_time=? WHERE visit_id=?", (t, v["visit_id"]))
            dur = (datetime.fromisoformat(t) - datetime.fromisoformat(v["entry_time"])).total_seconds() / 60
            res = {"action": "exit", "member": member, "time": t, "duration_min": round(dur, 1),
                   "message": f"Goodbye {member['name'].split()[0]}, you spent {int(dur)} min with us."}
        else:
            if st.conn.execute("SELECT COUNT(*) FROM visits WHERE exit_time IS NULL").fetchone()[0] >= CAPACITY:
                return {"error": "Library is at full capacity"}
            st.conn.execute("INSERT INTO visits(member_id, entry_time, exit_time, purpose) VALUES (?,?,NULL,?)",
                            (member_id, t, purpose))
            res = {"action": "entry", "member": member, "time": t, "duration_min": None,
                   "message": f"Welcome, {member['name'].split()[0]}!"}
        st.conn.commit()
        st.bump()
        return res

    @app.post("/api/gate/scan")
    def gate_scan():
        body = request.get_json(silent=True) or {}
        mid = str(body.get("member_id", "")).strip().upper()
        if not mid:
            return err("member_id is required")
        res = scan(mid, body.get("purpose"))
        if res is None:
            return err(f"Unknown member {mid}", 404)
        if "error" in res:
            return err(res["error"], 409)
        return ok(res)

    @app.post("/api/gate/simulate")
    def gate_simulate():
        n = max(1, min(40, int((request.get_json(silent=True) or {}).get("n", 8))))
        inside = [r["member_id"] for r in q("SELECT member_id FROM visits WHERE exit_time IS NULL")]
        everyone = [r["member_id"] for r in q("SELECT member_id FROM members")]
        events = []
        for _ in range(n):
            leave = inside and random.random() < min(0.6, len(inside) / 40)
            mid = random.choice(inside) if leave else random.choice(everyone)
            res = scan(mid, random.choice(["Study", "Reading", "Borrow/Return", "Research"]))
            if res and "error" not in res:
                events.append(res)
                (inside.remove(mid) if res["action"] == "exit" else inside.append(mid))
        return ok({"events": events})

    @app.get("/api/gate/live")
    def gate_live():
        now = datetime.now()
        inside = q("SELECT v.member_id, m.name, m.department, v.entry_time FROM visits v "
                   "JOIN members m USING(member_id) WHERE v.exit_time IS NULL ORDER BY v.entry_time DESC")
        for r in inside:
            r["minutes"] = round((now - datetime.fromisoformat(r["entry_time"])).total_seconds() / 60, 1)
        recent = q("""SELECT * FROM (
              SELECT v.member_id, m.name, 'entry' action, v.entry_time time, NULL duration_min
              FROM visits v JOIN members m USING(member_id)
              UNION ALL
              SELECT v.member_id, m.name, 'exit', v.exit_time,
                     ROUND((julianday(v.exit_time)-julianday(v.entry_time))*1440,1)
              FROM visits v JOIN members m USING(member_id) WHERE v.exit_time IS NOT NULL)
            WHERE time <= ? ORDER BY time DESC LIMIT 25""", now_iso())
        return ok({"inside": inside, "recent": recent, "capacity": CAPACITY})

    # ---------------- members ----------------
    @app.get("/api/members")
    def members():
        term = f"%{request.args.get('q', '').strip()}%"
        limit = min(500, int(request.args.get("limit", 50)))
        return ok(q("""SELECT m.member_id, m.name, m.department, m.year,
              (SELECT COUNT(*) FROM visits v WHERE v.member_id=m.member_id) visits,
              (SELECT COUNT(*) FROM loans l WHERE l.member_id=m.member_id) loans
            FROM members m WHERE m.member_id LIKE ? OR m.name LIKE ? OR m.department LIKE ?
            ORDER BY m.member_id LIMIT ?""", term, term, term, limit))

    @app.get("/api/members/<mid>")
    def member(mid):
        mid = mid.upper()
        m = q("SELECT * FROM members WHERE member_id=?", mid)
        if not m:
            return err("member not found", 404)
        visits = q("SELECT entry_time, exit_time, purpose, ROUND((julianday(exit_time)-julianday(entry_time))*1440,1) "
                   "duration_min FROM visits WHERE member_id=? ORDER BY entry_time DESC", mid)
        loans = q("SELECT l.loan_id, l.book_id, b.title, b.genre, l.issued, l.due, l.returned FROM loans l "
                  "JOIN books b USING(book_id) WHERE member_id=? ORDER BY issued DESC", mid)
        now = now_iso()
        for l in loans:
            l["status"] = "returned" if l["returned"] else ("overdue" if l["due"] < now else "on loan")
        closed = [v["duration_min"] for v in visits if v["duration_min"] is not None]
        returned = [l for l in loans if l["returned"]]
        genres = {}
        for l in loans:
            genres[l["genre"]] = genres.get(l["genre"], 0) + 1
        total = sum(genres.values()) or 1
        return ok({
            "member": m[0],
            "stats": {"visits": len(visits), "total_hours": sum(closed) / 60,
                      "avg_stay_min": float(np.mean(closed)) if closed else None,
                      "loans": len(loans),
                      "late_rate": (sum(l["returned"] > l["due"] for l in returned) / len(returned)) if returned else None,
                      "favourite_genre": max(genres, key=genres.get) if genres else None},
            "visits": visits[:30], "loans": loans,
            "taste": {g: c / total for g, c in sorted(genres.items(), key=lambda x: -x[1])},
        })

    # ---------------- books & loans ----------------
    @app.get("/api/genres")
    def genres():
        return ok([r["genre"] for r in q("SELECT DISTINCT genre FROM books ORDER BY genre")])

    BOOK_SQL = """SELECT b.*, b.copies - (SELECT COUNT(*) FROM loans l WHERE l.book_id=b.book_id AND l.returned IS NULL) available,
        (SELECT AVG(rating) FROM ratings r WHERE r.book_id=b.book_id) avg_rating,
        (SELECT COUNT(*) FROM ratings r WHERE r.book_id=b.book_id) n_ratings FROM books b"""

    @app.get("/api/books")
    def books():
        term, genre = f"%{request.args.get('q', '').strip()}%", request.args.get("genre", "")
        sql = BOOK_SQL + " WHERE (title LIKE ? OR author LIKE ? OR description LIKE ?)"
        args = [term, term, term]
        if genre:
            sql += " AND genre = ?"
            args.append(genre)
        return ok(q(sql + " ORDER BY title", *args))

    @app.get("/api/books/<int:bid>")
    def book(bid):
        b = q(BOOK_SQL + " WHERE book_id=?", bid)
        if not b:
            return err("book not found", 404)
        return ok({**b[0], "similar": st.recommender().similar(bid, 8)["items"]})

    @app.post("/api/loans")
    def issue():
        body = request.get_json(silent=True) or {}
        mid, bid = str(body.get("member_id", "")).upper(), body.get("book_id")
        if not q("SELECT 1 FROM members WHERE member_id=?", mid):
            return err("unknown member", 404)
        b = q(BOOK_SQL + " WHERE book_id=?", bid)
        if not b:
            return err("unknown book", 404)
        if b[0]["available"] <= 0:
            return err("no copies available", 409)
        if q("SELECT 1 FROM loans WHERE member_id=? AND book_id=? AND returned IS NULL", mid, bid):
            return err("member already has this book", 409)
        issued = datetime.now()
        cur = st.conn.execute("INSERT INTO loans(member_id, book_id, issued, due) VALUES (?,?,?,?)",
                              (mid, bid, issued.isoformat(timespec="seconds"),
                               (issued + timedelta(days=14)).isoformat(timespec="seconds")))
        st.conn.commit()
        st.bump()
        return ok(q("SELECT * FROM loans WHERE loan_id=?", cur.lastrowid)[0]), 201

    @app.post("/api/loans/<int:lid>/return")
    def return_loan(lid):
        if not q("SELECT 1 FROM loans WHERE loan_id=? AND returned IS NULL", lid):
            return err("loan not found or already returned", 404)
        st.conn.execute("UPDATE loans SET returned=? WHERE loan_id=?", (now_iso(), lid))
        st.conn.commit()
        st.bump()
        return ok(q("SELECT * FROM loans WHERE loan_id=?", lid)[0])

    # ---------------- recommender ----------------
    @app.get("/api/recommend/<mid>")
    def recommend(mid):
        method = request.args.get("method", "hybrid")
        if method not in METHODS:
            return err(f"method must be one of {METHODS}")
        mid = mid.upper()
        if not q("SELECT 1 FROM members WHERE member_id=?", mid):
            return err("member not found", 404)
        on_loan = [r["book_id"] for r in q("SELECT book_id FROM loans WHERE member_id=?", mid)]
        k = min(30, int(request.args.get("k", 10)))
        return ok(st.recommender().recommend(mid, method, k, exclude=on_loan))

    @app.get("/api/recommend/similar/<int:bid>")
    def similar(bid):
        rec = st.recommender()
        if bid not in rec.bidx:
            return err("book not found", 404)
        return ok(rec.similar(bid, min(20, int(request.args.get("k", 8)))))

    @app.get("/api/recommend/evaluate")
    def rec_evaluate():
        return ok(st.memo("rec_eval", lambda: evaluate(st.frames()), ttl_versions=10**9))

    # ---------------- analytics ----------------
    def analytic(name):
        from . import analytics
        return ok(st.memo(f"an_{name}", lambda: getattr(analytics, name)(st.frames()), ttl_versions=50))

    for _name in ("eda", "hypothesis", "forecast", "classify", "clusters"):
        app.add_url_rule(f"/api/analytics/{_name}", f"an_{_name}", lambda _n=_name: analytic(_n))

    @app.get("/api/occupancy/forecast")
    def occupancy():
        from . import analytics
        inside = st.conn.execute("SELECT COUNT(*) FROM visits WHERE exit_time IS NULL").fetchone()[0]
        fc = st.memo("an_forecast", lambda: analytics.forecast(st.frames()), ttl_versions=50)
        return ok(analytics.occupancy_forecast(st.frames(), inside, CAPACITY, fc))

    @app.post("/api/analytics/predict_late")
    def predict_late():
        from . import analytics
        body = request.get_json(silent=True) or {}
        try:
            return ok(analytics.predict_late(st.frames(), str(body.get("member_id", "")).upper(), int(body.get("book_id"))))
        except (KeyError, ValueError, TypeError, IndexError) as e:
            return err(f"cannot score: {e}")

    # ---------------- graph & ethics ----------------
    @app.get("/api/graph/books")
    def graph_books():
        w = int(request.args.get("min_weight", 3))
        return ok(st.memo(f"graph_{w}", lambda: graph.co_borrow_graph(st.frames(), w), ttl_versions=50))

    @app.get("/api/graph/cypher")
    def graph_cypher():
        return Response(graph.cypher_script(st.frames()), mimetype="text/plain")

    @app.get("/api/ethics/report")
    def ethics_report():
        return ok(st.memo("ethics", lambda: ethics.report(st.frames(), st.recommender()), ttl_versions=50))

    return app
