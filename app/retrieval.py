"""第5回: ページ単位のベクトル検索。"""

import argparse
import json
import math
import re
import sqlite3
from contextlib import contextmanager
from collections import Counter, defaultdict, deque
from pathlib import Path

from google import genai
from google.genai import types
from pydantic_ai.exceptions import ModelHTTPError
import sqlite_vec

from app.config import (
    EMBEDDING_DIMENSIONS, EMBEDDING_MAX_TOKENS, EMBEDDING_MODEL,
    RAG_DB, RAG_DOCUMENT_IDS, RAG_NEIGHBOR_PAGES, RAG_SOURCE, RAG_TOP_K, RAG_TREE, get_api_key,
    RAG_GRAPH, GRAPH_START_K, GRAPH_HOPS, GRAPH_MAX_RESULTS,
)


def get_all_materials() -> str:
    """全資料を、講義・章・ページの情報付きで1つの文字列にまとめる。"""
    documents = json.loads(RAG_SOURCE.read_text(encoding="utf-8"))
    return "\n\n".join(
        f"資料: {document['id']} / {document['title']}\n"
        f"章: {section['section']}\n"
        f"ページ: PDF p.{page['page']} / {page['title']}\n{page['content']}"
        for document in documents
        for section in document["content"]
        for page in section["content"]
    )

def load_pages(source: Path = RAG_SOURCE) -> list[dict]:
    """資料→章→ページのJSONを、対象資料のページ一覧に変換する。"""
    documents = json.loads(source.read_text(encoding="utf-8"))
    pages = []
    for document in documents:
        if document["id"] not in RAG_DOCUMENT_IDS:
            continue
        for section in document["content"]:
            for page in section["content"]:
                pages.append({"page_id": page["id"], "document_id": document["id"],
                              "lecture": int(document["id"][3:5]), "document_title": document["title"],
                              "section": section["section"], "title": page["title"],
                              "page": page["page"], "content": page["content"]})
    return pages


def lead_sentence(text: str) -> str:
    """本文の先頭文。句点がなければ先頭行（browse_tree の候補文と同じ規則）。"""
    return re.split(r"(?<=[。！？])|\n", text.strip(), maxsplit=1)[0]


def browse_tree(node_id: str | None = None) -> dict:
    """直下のページは先頭文、指定したページ自身は全文を返す。"""
    tree = json.loads(RAG_TREE.read_text(encoding="utf-8"))
    tree["children"] = [node for node in tree["children"] if node["id"] in RAG_DOCUMENT_IDS]
    node_id = node_id or tree["id"]
    pages = {page["page_id"]: page for page in load_pages(RAG_SOURCE)}

    def describe(node, full=False):
        info = {key: node[key] for key in ("id", "kind", "title")}
        if node["kind"] == "page":
            info.update({key: value for key, value in pages[node["id"]].items() if key != "page_id"})
            if not full:
                info["content"] = lead_sentence(info["content"])
        return info

    remaining = [tree]
    while remaining:
        node = remaining.pop()
        if node["id"] == node_id:
            return {
                "node": describe(node, full=True),
                "children": [describe(child) for child in node.get("children", [])],
            }
        remaining.extend(node.get("children", []))
    raise ValueError("対象の目次ノードが見つかりません。")


def read_page(page_id: str) -> dict:
    """第1〜3回の本講義から、指定した1ページの本文と引用情報を返す。"""
    for page in load_pages(RAG_SOURCE):
        if page["page_id"] == page_id:
            return page
    raise ValueError("対象のページが見つかりません。")


def normalized_vector(values: list[float]) -> list[float]:
    """ベクトルの長さを1に揃える。"""
    norm = math.hypot(*values)
    if norm == 0:
        raise ValueError("埋め込みがゼロベクトルです。")
    return [value / norm for value in values]


def embed_text(text: str, task_type: str) -> list[float]:
    """Geminiで文章を埋め込む。入力上限を超えた場合は切り捨てず停止する。"""
    with genai.Client(api_key=get_api_key()) as client:
        count = client.models.count_tokens(model=EMBEDDING_MODEL, contents=text).total_tokens
        if count is None or count > EMBEDDING_MAX_TOKENS:
            raise ValueError(f"埋め込み入力が上限を超えるか計測不能です: {count} tokens。")
        response = client.models.embed_content(
            model=EMBEDDING_MODEL, contents=text,
            config=types.EmbedContentConfig(task_type=task_type, output_dimensionality=EMBEDDING_DIMENSIONS),
        )
    embedding = response.embeddings[0]
    if embedding.statistics and embedding.statistics.truncated:
        raise ValueError("埋め込みAPIが本文を切り捨てました。")
    return normalized_vector(embedding.values)


@contextmanager
def open_index(path: Path):
    """既存の検索DBを読み取り専用で開き、終了時に閉じる。"""
    if not path.is_file():
        raise FileNotFoundError("検索DBがありません。")
    db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        db.row_factory = sqlite3.Row
        db.enable_load_extension(True)
        sqlite_vec.load(db)
        db.enable_load_extension(False)
        yield db
    finally:
        db.close()


def search(query: str) -> list[dict]:
    """質問を埋め込み、近いページを最大RAG_TOP_K件返す。RAG_NEIGHBOR_PAGES > 0 なら前後ページも付ける。"""
    hits = vector_search(query)
    if RAG_NEIGHBOR_PAGES > 0:
        hits = add_neighbors(hits, load_pages(RAG_SOURCE), RAG_NEIGHBOR_PAGES)
    return hits


def vector_search(query: str) -> list[dict]:
    """質問を埋め込み、近いページを最大RAG_TOP_K件返す（前後ページは付けない。Graph の入口にも使う）。"""
    if not isinstance(query, str) or not query.strip():
        raise ValueError("検索語が空です。")
    with open_index(RAG_DB) as db:
        vector = embed_text(query.strip(), "RETRIEVAL_QUERY")
        rows = db.execute("""
            SELECT page_id, document_id, lecture, document_title, section, title, page, content,
                   vec_distance_cosine(embedding, ?) AS distance
            FROM chunks ORDER BY distance, page_id LIMIT ?
        """, (sqlite_vec.serialize_float32(vector), RAG_TOP_K))
        return [dict(row) for row in rows]


def add_neighbors(hits: list[dict], pages: list[dict], width: int = 1) -> list[dict]:
    """第5回 宿題（実装）: 検索で見つかった各ページの直後に、同じ資料の前後 width ページの本文を足す。

    - 前後は同じ document_id の中だけで探す（資料をまたがない。第2回の p.1 の前に第1回の最後のページを付けない）
    - すでに入っているページ（検索結果どうしが隣り合う場合や、2 つの検索結果に共通の隣）は足さない
    - 足したページには source="neighbor" と、どの検索結果の隣か（neighbor_of）を付ける。distance は持たない
    検索結果の順位と件数（RAG_TOP_K）は変えない。
    """
    by_position = {(page["document_id"], page["page"]): page for page in pages}
    included = {hit["page_id"] for hit in hits}
    results = []
    for hit in hits:
        results.append({**hit, "source": "search"})
        for offset in [o for d in range(1, width + 1) for o in (-d, d)]:   # 前1, 後1, 前2, 後2, ...
            page = by_position.get((hit["document_id"], hit["page"] + offset))
            if page is None or page["page_id"] in included:
                continue
            included.add(page["page_id"])
            results.append({**page, "distance": None, "source": "neighbor", "neighbor_of": hit["page_id"]})
    return results


# 目次を付ける章：1 位のページがある章と、ヒットが OUTLINE_MIN_HITS 件以上ある章（v3）。1 なら全部の章（v1・v2）
OUTLINE_MIN_HITS = 2


def search_outline(query: str, lead: bool = False, min_hits: int | None = None) -> dict:
    """第5回 宿題（発展）: ベクトル検索の結果に、各ページがある章の目次（ページ番号とタイトルだけ）を付けて返す。

    - results：ベクトル検索の上位 RAG_TOP_K 件（本文つき。search と同じ。前後ページは付けない）
    - outlines：results のページが属する章ごとに、その章の全ページの page_id・page・title。本文は含めない。
      in_results は、そのページの本文が results に入っているか
    lead=True なら、目次の各ページに先頭文（lead）も付ける（v2。章の構成なら本文を読まずに答えられる）。
    min_hits（既定 OUTLINE_MIN_HITS）：目次を付けるのは、1 位のページがある章と、ヒットが min_hits 件以上ある章だけ（v3）。
    ヒットが多くの章に散る質問（資料にない質問など）で、目次が章の数だけ膨らむのを防ぐ。
    目次にあって本文のないページは、v1 では browse_tree(page_id)、v2 では read_pages で全文を読む。データは tree.json と検索DBをそのまま使い、
    新しい索引は作らない。章の直下ではなく講義の直下にあるページ（第2回の p.1〜6 など）は、講義の直下のページだけを並べる。
    """
    hits = vector_search(query)
    tree = json.loads(RAG_TREE.read_text(encoding="utf-8"))
    pages = {page["page_id"]: page for page in load_pages(RAG_SOURCE)} if lead else {}
    parent = {}
    remaining = [node for node in tree["children"] if node["id"] in RAG_DOCUMENT_IDS]
    while remaining:
        node = remaining.pop()
        for child in node.get("children", []):
            parent[child["id"]] = node
            remaining.append(child)
    hit_ids = {hit["page_id"] for hit in hits}
    min_hits = OUTLINE_MIN_HITS if min_hits is None else min_hits
    counts = Counter(parent[hit["page_id"]]["id"] for hit in hits if hit["page_id"] in parent)
    outlines, seen = [], set()
    for rank, hit in enumerate(hits):
        node = parent.get(hit["page_id"])
        if node is None or node["id"] in seen or (rank > 0 and counts[node["id"]] < min_hits):
            continue
        seen.add(node["id"])
        outlines.append({
            "section_id": node["id"], "lecture": hit["lecture"], "section": node["title"],
            "pages": [{"page_id": child["id"], "page": child["page"], "title": child["title"],
                       **({"lead": lead_sentence(pages[child["id"]]["content"])} if lead else {}),
                       "in_results": child["id"] in hit_ids}
                      for child in node.get("children", []) if child["kind"] == "page"],
        })
    return {"results": hits, "outlines": outlines}


READ_PAGES_MAX = 10


def read_pages(page_ids: list[str]) -> dict:
    """第5回 宿題（発展 v2）: 指定した複数ページの本文と引用情報を、1 回でまとめて返す（重複は除く。最大 READ_PAGES_MAX）。"""
    if not page_ids:
        raise ValueError("page_ids が空です。")
    pages = {page["page_id"]: page for page in load_pages(RAG_SOURCE)}
    wanted = list(dict.fromkeys(page_ids))
    return {"pages": [pages[pid] for pid in wanted[:READ_PAGES_MAX] if pid in pages],
            "not_found": [pid for pid in wanted if pid not in pages],
            "skipped": wanted[READ_PAGES_MAX:]}


def search_graph(query: str) -> dict:
    """ベクトル検索を入口に、前後ページと共通用語で候補を広げる。"""
    pages = {page["page_id"]: page for page in load_pages(RAG_SOURCE)}
    graph = json.loads(RAG_GRAPH.read_text(encoding="utf-8"))
    nodes = {node["id"]: node for node in graph["nodes"]
             if node["kind"] == "term" or node["id"] in pages}
    adjacent = defaultdict(set)
    for edge in graph["edges"]:
        a, b = edge["source"], edge["target"]
        if edge["relation"] in ("next_page", "mentions") and a in nodes and b in nodes:
            adjacent[a].add(b)
            adjacent[b].add(a)

    seeds = [hit for hit in vector_search(query) if hit["page_id"] in pages][:min(GRAPH_START_K, GRAPH_MAX_RESULTS)]
    seed_ids = {seed["page_id"] for seed in seeds}
    results, candidates = [], {}
    for rank, seed in enumerate(seeds):
        root = seed["page_id"]
        results.append({**pages[root], "distance": seed["distance"], "hops": 0,
                        "path": [{"id": root, "title": pages[root]["title"]}]})
        queue = deque([(root, [root])])
        visited = {root}
        while queue:
            current, path = queue.popleft()
            if len(path) - 1 >= GRAPH_HOPS:
                continue
            # 同じ深さなら、接続先が少ない用語からたどる。
            neighbors = sorted(adjacent[current], key=lambda n: (len(adjacent[n]), n))
            for neighbor in neighbors:
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                route = path + [neighbor]
                queue.append((neighbor, route))
                if neighbor not in pages or neighbor in seed_ids:
                    continue
                frequency = max((len(adjacent[n]) for n in route if nodes[n]["kind"] == "term"), default=0)
                priority = (len(route) - 1, frequency, rank, neighbor)
                candidate = {**pages[neighbor], "hops": len(route) - 1,
                             "path": [{"id": n, "title": nodes[n]["title"]} for n in route]}
                if neighbor not in candidates or priority < candidates[neighbor][0]:
                    candidates[neighbor] = (priority, candidate)
    expanded = [candidate for _, candidate in sorted(candidates.values())]
    return {"seeds": results, "expanded": expanded[:max(0, GRAPH_MAX_RESULTS - len(results))],
            "max_hops": GRAPH_HOPS}



def run_full_context(agent, question: str, model, instructions: str, prompt_template: str):
    """全資料を一括投入し、検索ツールを使わずに回答する。"""
    prompt = prompt_template.format(materials=get_all_materials(), question=question)
    print(f"[full-context] 入力{len(prompt):,}文字")
    try:
        with agent.override(tools=[], instructions=instructions):
            return agent.run_sync(prompt, model=model)
    except ModelHTTPError as e:
        print(f"[full-context] APIエラー HTTP {e.status_code}: {e.body}")
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="エージェントを使わず、講義資料の検索だけを実行する")
    parser.add_argument("query", help="調べたい内容")
    args = parser.parse_args()
    for i, result in enumerate(search(args.query), 1):
        print(f"\n{'=' * 60}\n検索結果 {i}\n{'=' * 60}")
        print(f"講義: {result['document_title']}")
        print(f"章: {result['section']}")
        print(f"タイトル: {result['title']}")
        print(f"ページ: {result['page']}")
        if result.get("source") == "neighbor":
            print(f"（前後ページ: {result['neighbor_of']} の隣として追加）")
        print(f"\n{result['content']}")
