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


# ---------------------------------------------------------------- 第5回 宿題（発展）: search_outline
def test_search_outline_returns_hits_and_the_outline_of_each_section(monkeypatch):
    # 第3回の Part 4 ツール（p.22〜32）から 2 ページ、Part 6 メモリから 1 ページがヒットした場合
    hits = [{"page_id": "lec03-main-p023", "lecture": 3, "page": 23},
            {"page_id": "lec03-main-p030", "lecture": 3, "page": 30},
            {"page_id": "lec03-main-p039", "lecture": 3, "page": 39}]
    monkeypatch.setattr(retrieval, "vector_search", lambda query: hits)
    data = retrieval.search_outline("q", min_hits=1)                   # v1・v2 と同じく、ヒットのある章すべて
    assert data["results"] == hits                                     # 本文はベクトル検索の結果そのまま
    assert [o["section_id"] for o in data["outlines"]] == ["lec03-main-s022", "lec03-main-s037"]  # 章ごとに 1 回
    tools_outline = data["outlines"][0]
    assert [p["page"] for p in tools_outline["pages"]] == list(range(22, 33))
    assert [p["page"] for p in tools_outline["pages"] if p["in_results"]] == [23, 30]
    assert all("content" not in p for p in tools_outline["pages"])    # 目次には本文を入れない


def test_search_outline_for_a_page_directly_under_the_lecture(monkeypatch):
    # 第2回の p.4 は章ではなく講義の直下にある。講義の直下のページだけを並べ、章のノードは含めない
    monkeypatch.setattr(retrieval, "vector_search", lambda query: [{"page_id": "lec02-main-p004", "lecture": 2, "page": 4}])
    outline = retrieval.search_outline("q")["outlines"][0]
    assert outline["section_id"] == "lec02-main"
    assert [p["page"] for p in outline["pages"]] == [1, 2, 3, 4, 5, 6]


def test_search_outline_with_lead_adds_first_sentence(monkeypatch):
    monkeypatch.setattr(retrieval, "vector_search", lambda query: [{"page_id": "lec03-main-p023", "lecture": 3, "page": 23}])
    pages = retrieval.search_outline("q", lead=True)["outlines"][0]["pages"]
    assert all(p["lead"] and "\n" not in p["lead"] for p in pages)
    assert "lead" not in retrieval.search_outline("q")["outlines"][0]["pages"][0]   # v1（lead なし）は変わらない


def test_read_pages_returns_several_pages_once_each():
    data = retrieval.read_pages(["lec03-main-p025", "lec03-main-p026", "lec03-main-p025", "lec09-main-p001"])
    assert [p["page_id"] for p in data["pages"]] == ["lec03-main-p025", "lec03-main-p026"]
    assert data["not_found"] == ["lec09-main-p001"] and data["skipped"] == []
    many = [f"lec03-main-p{n:03d}" for n in range(20, 33)]
    data = retrieval.read_pages(many)
    assert len(data["pages"]) == retrieval.READ_PAGES_MAX and data["skipped"] == many[retrieval.READ_PAGES_MAX:]


def test_outline_only_for_top_section_and_sections_with_two_hits(monkeypatch):
    # 1 位は Part 6（1 件）、Part 4 に 2 件、Part 2 に 1 件 → v3 は Part 6（1 位）と Part 4（2 件）だけ
    hits = [{"page_id": "lec03-main-p039", "lecture": 3, "page": 39},
            {"page_id": "lec03-main-p023", "lecture": 3, "page": 23},
            {"page_id": "lec03-main-p013", "lecture": 3, "page": 13},
            {"page_id": "lec03-main-p030", "lecture": 3, "page": 30}]
    monkeypatch.setattr(retrieval, "vector_search", lambda query: hits)
    assert [o["section_id"] for o in retrieval.search_outline("q", min_hits=2)["outlines"]] == \
        ["lec03-main-s037", "lec03-main-s022"]
    assert len(retrieval.search_outline("q", min_hits=1)["outlines"]) == 3
