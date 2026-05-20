from pipeline.scraper.search_queries import all_queries, get_daily_queries, CATEGORIES, DISTRICTS
from api.db import init_db


def test_all_queries_count():
    queries = all_queries()
    assert len(queries) == len(CATEGORIES) * len(DISTRICTS)


def test_all_queries_shape():
    q = all_queries()[0]
    assert "query" in q
    assert "category" in q
    assert "district" in q


def test_get_daily_queries_default_limit(tmp_path):
    conn = init_db(path=str(tmp_path / "test.db"))
    queries = get_daily_queries(conn)
    assert len(queries) == 22


def test_get_daily_queries_excludes_recent(tmp_path):
    conn = init_db(path=str(tmp_path / "test.db"))
    first_query = all_queries()[0]["query"]
    conn.execute(
        "INSERT INTO search_runs (query, results) VALUES (?, ?)",
        (first_query, 5),
    )
    conn.commit()
    queries = get_daily_queries(conn)
    assert all(q["query"] != first_query for q in queries)


def test_get_daily_queries_fallback_when_all_recent(tmp_path):
    conn = init_db(path=str(tmp_path / "test.db"))
    for q in all_queries():
        conn.execute(
            "INSERT INTO search_runs (query, results) VALUES (?, ?)",
            (q["query"], 0),
        )
    conn.commit()
    queries = get_daily_queries(conn)
    assert len(queries) == 22
