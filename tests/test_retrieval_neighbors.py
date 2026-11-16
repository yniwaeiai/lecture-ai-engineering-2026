"""第5回 宿題（実装）: 検索結果に前後ページを付ける処理（add_neighbors）のテスト。APIは呼ばない。"""

from app import retrieval


def _page(doc, page):
    return {"page_id": f"{doc}-p{page:03d}", "document_id": doc, "lecture": int(doc[3:5]),
            "document_title": doc, "section": "章", "title": f"{doc} {page}", "page": page,
            "content": f"本文 {doc} {page}"}


PAGES = [_page("lec01-main", n) for n in (1, 2, 3)] + [_page("lec02-main", n) for n in (1, 2, 3, 4, 5)]


def _hit(doc, page, distance=0.1):
    return {**_page(doc, page), "distance": distance}


def test_neighbors_are_added_after_each_hit_with_their_origin():
    results = retrieval.add_neighbors([_hit("lec02-main", 3)], PAGES)
    assert [r["page_id"] for r in results] == ["lec02-main-p003", "lec02-main-p002", "lec02-main-p004"]
    assert results[0]["source"] == "search" and results[0]["distance"] == 0.1
    assert all(r["source"] == "neighbor" and r["neighbor_of"] == "lec02-main-p003" and r["distance"] is None
               for r in results[1:])


def test_neighbors_do_not_cross_documents():
    # 第2回の p.1 の前に、第1回の最後のページ（p.3）を付けない。資料の最後のページの後ろにも付けない
    results = retrieval.add_neighbors([_hit("lec02-main", 1), _hit("lec01-main", 3)], PAGES)
    ids = [r["page_id"] for r in results]
    assert ids == ["lec02-main-p001", "lec02-main-p002", "lec01-main-p003", "lec01-main-p002"]


def test_no_page_appears_twice():
    # p.2 と p.4 が両方ヒット → 共通の隣 p.3 は 1 回だけ。ヒットどうしが隣（p.4 と p.5）でも重ねない
    hits = [_hit("lec02-main", 2), _hit("lec02-main", 4), _hit("lec02-main", 5)]
    ids = [r["page_id"] for r in retrieval.add_neighbors(hits, PAGES)]
    assert len(ids) == len(set(ids))
    assert ids == ["lec02-main-p002", "lec02-main-p001", "lec02-main-p003", "lec02-main-p004", "lec02-main-p005"]
    # 検索結果の順位は変わらない
    assert [r["page_id"] for r in retrieval.add_neighbors(hits, PAGES) if r["source"] == "search"] == \
        [h["page_id"] for h in hits]


def test_width_two_adds_pages_in_order_of_distance():
    ids = [r["page_id"] for r in retrieval.add_neighbors([_hit("lec02-main", 3)], PAGES, width=2)]
    assert ids == ["lec02-main-p003", "lec02-main-p002", "lec02-main-p004", "lec02-main-p001", "lec02-main-p005"]


def test_search_adds_neighbors_only_when_enabled(monkeypatch):
    monkeypatch.setattr(retrieval, "vector_search", lambda query: [_hit("lec02-main", 3)])
    monkeypatch.setattr(retrieval, "load_pages", lambda *_: PAGES)
    monkeypatch.setattr(retrieval, "RAG_NEIGHBOR_PAGES", 0)
    assert [r["page_id"] for r in retrieval.search("q")] == ["lec02-main-p003"]   # 既定は配布版と同じ
    monkeypatch.setattr(retrieval, "RAG_NEIGHBOR_PAGES", 1)
    assert len(retrieval.search("q")) == 3


def test_real_materials_have_no_gaps_inside_documents():
    # 前後を「ページ番号 ±1」で探すので、対象資料のページ番号が連番であることを確かめておく
    pages = retrieval.load_pages()
    for doc in {p["document_id"] for p in pages}:
        numbers = sorted(p["page"] for p in pages if p["document_id"] == doc)
        assert numbers == list(range(numbers[0], numbers[-1] + 1)), doc
