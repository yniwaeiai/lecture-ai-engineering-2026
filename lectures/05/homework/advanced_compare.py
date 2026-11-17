"""第5回 宿題（発展）: 目次付き検索（--hybrid）を、基本RAG（ベクトル検索）・Tree・Graph と同じ質問で比べる。

狙いの質問は、基本RAGの上位 5 件では足りない「章の構成」（Q6・Q7）と「章をまたぐ列挙」（Q5）。
単一ページ（Q1）・複数ページ（Q2）・資料にない（Q3）も、悪くならないかの確認に入れる。
対象資料は 4 方式とも第1〜3回の本講義 214 ページ。モデル・RAG_TOP_K=5・前後ページなし（RAG_NEIGHBOR_PAGES=0）でそろえる。

使い方（リポジトリ直下で。要 GEMINI_API_KEY）:
    uv run python lectures/05/homework/advanced_compare.py --reps 2
    uv run python lectures/05/homework/advanced_compare.py --report
"""

import argparse

from common import (CHAPTER_PAGES, QUESTIONS, RESULTS, SUFFICIENT, append_run, chapter_coverage, coverage,
                    load_runs, mean, run_once)

import app.retrieval as retrieval
from app import tools
from app.agent import GRAPH_INSTRUCTIONS, HYBRID_INSTRUCTIONS, HYBRID_V1_INSTRUCTIONS, TREE_INSTRUCTIONS, agent

METHODS = {
    "vector": None,
    "tree": (TREE_INSTRUCTIONS, [tools.browse_tree]),
    "graph": (GRAPH_INSTRUCTIONS, [tools.search_graph]),
    # v1：目次はタイトルだけ、本文は browse_tree で読む。v2：目次に先頭文、本文は read_pages でまとめて読む（technical-memo 4.5）
    "hybrid": (HYBRID_V1_INSTRUCTIONS, [tools.search_outline, tools.browse_tree]),
    "hybrid2": (HYBRID_INSTRUCTIONS, [tools.search_chapters, tools.read_pages]),          # OUTLINE_MIN_HITS=1
    # v3：v2 と同じ道具と指示文。目次を付ける章を「1 位の章＋ヒット 2 件以上の章」に絞った（OUTLINE_MIN_HITS=2）
    "hybrid3": (HYBRID_INSTRUCTIONS, [tools.search_chapters, tools.read_pages]),
}
OUTLINE_MIN_HITS = {"hybrid2": 1, "hybrid3": 2}
QIDS = ["Q1", "Q2", "Q3", "Q5", "Q6", "Q7"]
OUT = RESULTS / "advanced_runs.jsonl"


def run_method(method: str, question: str) -> dict:
    spec = METHODS[method]
    if spec is None:
        return run_once(agent, question)
    instructions, tool_list = spec
    retrieval.OUTLINE_MIN_HITS = OUTLINE_MIN_HITS.get(method, 2)
    with agent.override(instructions=instructions, tools=tool_list):
        return run_once(agent, question)


def sufficient(record, qid):
    pages = {pid for r in record.get("tool_returns", []) for pid in r["page_ids"]}
    need = SUFFICIENT.get(qid)
    return None if need is None else sum(p in pages for p in need)


def report(runs):
    print(f"{'質問':4} {'方式':8} {'回':>2}  本文取得/根拠  一覧で見た/根拠  回答のページ  ツール回数  時間    入力tok  出力tok  応答  費用(キャッシュなし)")
    for qid in QIDS:
        for method in METHODS:
            rs = [r for r in runs if r["qid"] == qid and r["method"] == method and "error" not in r]
            if not rs:
                continue
            cov = [coverage(r, qid) for r in rs]
            of = cov[0]["of"]
            if qid in CHAPTER_PAGES:
                answer_pages = f"{mean([chapter_coverage(r, qid) for r in rs]):4.1f}/{of}"
            else:
                answer_pages = f"{mean([c['cited'] for c in cov]):4.1f}/{of}"
            extra = ""
            if qid in SUFFICIENT:
                extra = f"（答えのページ {mean([sufficient(r, qid) for r in rs]):.1f}/{len(SUFFICIENT[qid])}）"
            print(f"{qid:4} {method:8} {len(rs):>2}  {mean([c['retrieved'] for c in cov]):5.1f}/{of:<3}    {mean([c['listed_or_retrieved'] for c in cov]):5.1f}/{of:<3}"
                  f"       {answer_pages}     {mean([len(r['tool_calls']) for r in rs]):5.1f}    {mean([r['elapsed'] for r in rs]):5.2f}s  {mean([r['input_tokens'] for r in rs]):7,.0f}  {mean([r['output_tokens'] for r in rs]):6,.0f}"
                  f"  {mean([r['requests'] for r in rs]):4.1f}  ${mean([r['cost_uncached'] for r in rs]):.6f} {extra}")
    errors = [r for r in runs if "error" in r]
    if errors:
        print(f"\nAPI エラー {len(errors)} 件")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=2)
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()
    retrieval.RAG_TOP_K, retrieval.RAG_NEIGHBOR_PAGES = 5, 0
    runs = load_runs(OUT)
    if not args.report:
        for rep in range(args.reps):
            for qid in QIDS:
                for method in METHODS:
                    if any(r["qid"] == qid and r["method"] == method and r["rep"] == rep for r in runs):
                        continue
                    record = {"qid": qid, "method": method, "rep": rep, **run_method(method, QUESTIONS[qid])}
                    append_run(OUT, record)
                    runs.append(record)
                    print(f"{qid} {method} rep{rep}: {coverage(record, qid) if 'error' not in record else record['error']} {record.get('elapsed')}s")
    report(runs)


if __name__ == "__main__":
    main()
