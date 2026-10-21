"""Book co-borrowing graph + Cypher export for Neo4j."""
from collections import Counter
from itertools import combinations


def co_borrow_graph(frames, min_weight=3):
    loans, books = frames["loans"], frames["books"]
    pairs = Counter()
    for _, ids in loans.groupby("member_id")["book_id"]:
        for a, b in combinations(sorted(set(ids)), 2):
            pairs[(a, b)] += 1
    links = [{"source": int(a), "target": int(b), "weight": w} for (a, b), w in pairs.items() if w >= min_weight]
    used = {l["source"] for l in links} | {l["target"] for l in links}
    counts = loans["book_id"].value_counts()
    nodes = [{"id": int(r.book_id), "title": r.title, "genre": r.genre, "loans": int(counts.get(r.book_id, 0))}
             for r in books.itertuples() if r.book_id in used]
    return {"nodes": nodes, "links": links}


def _q(s):
    return "'" + str(s).replace("\\", "\\\\").replace("'", "\\'") + "'"


def cypher_script(frames, min_weight=2):
    """MERGE statements for (:Member)-[:BORROWED]->(:Book)-[:IN_GENRE]->(:Genre)
    and (:Book)-[:CO_BORROWED {weight}]-(:Book). Members are pseudonymised."""
    from .ethics import pseudonym
    lines = ["// Athenaeum library graph - paste into Neo4j Browser",
             "CREATE CONSTRAINT IF NOT EXISTS FOR (b:Book) REQUIRE b.id IS UNIQUE;",
             "CREATE CONSTRAINT IF NOT EXISTS FOR (m:Member) REQUIRE m.token IS UNIQUE;"]
    for g in sorted(frames["books"].genre.unique()):
        lines.append(f"MERGE (:Genre {{name: {_q(g)}}});")
    for b in frames["books"].itertuples():
        lines.append(f"MERGE (b:Book {{id: {b.book_id}}}) SET b.title = {_q(b.title)}, b.author = {_q(b.author)} "
                     f"WITH b MATCH (g:Genre {{name: {_q(b.genre)}}}) MERGE (b)-[:IN_GENRE]->(g);")
    for m in frames["members"].itertuples():
        lines.append(f"MERGE (:Member {{token: {_q(pseudonym(m.member_id))}, department: {_q(m.department)}}});")
    for l in frames["loans"].drop_duplicates(["member_id", "book_id"]).itertuples():
        lines.append(f"MATCH (m:Member {{token: {_q(pseudonym(l.member_id))}}}), (b:Book {{id: {l.book_id}}}) "
                     f"MERGE (m)-[:BORROWED]->(b);")
    for e in co_borrow_graph(frames, min_weight)["links"]:
        lines.append(f"MATCH (a:Book {{id: {e['source']}}}), (b:Book {{id: {e['target']}}}) "
                     f"MERGE (a)-[:CO_BORROWED {{weight: {e['weight']}}}]-(b);")
    lines += ["", "// Example queries",
              "// MATCH (b:Book)-[r:CO_BORROWED]-(o) RETURN b.title, o.title, r.weight ORDER BY r.weight DESC LIMIT 10;",
              "// MATCH (m:Member)-[:BORROWED]->(:Book)-[:IN_GENRE]->(g) RETURN g.name, count(*) AS loans ORDER BY loans DESC;"]
    return "\n".join(lines)
