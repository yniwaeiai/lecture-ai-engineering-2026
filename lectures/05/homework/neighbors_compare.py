"""第5回 宿題（実装）: 検索結果に前後 1 ページの本文を付ける（RAG_NEIGHBOR_PAGES=1）と、通常の検索（0）を比べる。

既定のエージェント（search_materials だけを持つ）・RAG_TOP_K=5・同じ質問で比べる。ツールの docstring と指示文は変えない。
CLI では AIE_RAG_NEIGHBORS=1 で同じ動きになる（--trace の実行例はそれで取った。technical-memo 3.3）。

使い方（リポジトリ直下で。要 GEMINI_API_KEY）:
    uv run python lectures/05/homework/neighbors_compare.py --reps 3
    uv run python lectures/05/homework/neighbors_compare.py --report
"""

import argparse

from common import EVIDENCE, QUESTIONS, RESULTS, append_run, coverage, load_runs, mean, page_key, run_once

import app.retrieval as retrieval
from app.agent import agent

# (RAG_TOP_K, RAG_NEIGHBOR_PAGES)。K=5 の 2 つが本来の比較。K=3 の 2 つは、K=3 で 1 回目の検索から漏れた根拠
# （Q2 の p.40。基礎 b で観察）を前後ページが補えるかを見るために後から足した（technical-memo 3.4）
MODES = [(5, 0), (5, 1), (3, 0), (3, 1)]
QIDS = ["Q1", "Q2", "Q3", "Q4", "Q5"]
OUT = RESULTS / "neighbors_runs.jsonl"


def neighbor_only_evidence(record: dict, qid: str) -> int:
    """根拠ページのうち、検索の上位には無く、前後ページとしてだけ入ったものの数（前後ページで根拠が増えた数）。

    run_once は tool_returns に page_id の並びしか残さないので、検索の上位 5 件かどうかは
    「各ツール結果の、source が search のページ」を JSON から数え直す必要がある。そのため記録時に
    search_ids / neighbor_ids を別に残している（main を参照）。
    """
    hits = set(record.get("search_ids", []))
    neighbors = set(record.get("neighbor_ids", []))
    return sum(pid in neighbors and pid not in hits for pid in EVIDENCE[qid])


def report(runs):
    print(f"{'質問':4} {'K/前後':>5} {'回':>2}  根拠の取得/引用(平均)  前後でだけ取れた根拠  検索回数  返ったページ(異なり)  時間    入力tok  出力tok  応答  費用(キャッシュなし)  引用した前後ページ")
    for qid in QIDS:
        for mode in MODES:
            k, n = mode
            rs = [r for r in runs if r["qid"] == qid and (r.get("k", 5), r["neighbors"]) == mode and "error" not in r]
            if not rs:
                continue
            cov = [coverage(r, qid) for r in rs]
            of = cov[0]["of"]
            cited_neighbors = sorted({c for r in rs for c in r["cited"]
                                      if c in {page_key(p) for p in r.get("neighbor_ids", []) if p.startswith("lec")}
                                      and c not in {page_key(p) for p in r.get("search_ids", [])}})
            print(f"{qid:4} K{k}/{n:>1} {len(rs):>2}  {mean([c['retrieved'] for c in cov]):.1f}/{of} , {mean([c['cited'] for c in cov]):.1f}/{of}"
                  f"           {mean([neighbor_only_evidence(r, qid) for r in rs]):.1f}"
                  f"              {mean([len(r['tool_calls']) for r in rs]):.1f}      {mean([c['unique_pages_returned'] for c in cov]):5.1f}"
                  f"          {mean([r['elapsed'] for r in rs]):5.2f}s  {mean([r['input_tokens'] for r in rs]):7,.0f}  {mean([r['output_tokens'] for r in rs]):6,.0f}"
                  f"  {mean([r['requests'] for r in rs]):.1f}  ${mean([r['cost_uncached'] for r in rs]):.6f}         {', '.join(cited_neighbors) or '-'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()
    runs = load_runs(OUT)
    if not args.report:
        original_search = retrieval.search
        for rep in range(args.reps):
            for qid in QIDS:
                for k, n in MODES:
                    if any(r["qid"] == qid and (r.get("k", 5), r["neighbors"]) == (k, n) and r["rep"] == rep for r in runs):
                        continue
                    retrieval.RAG_TOP_K, retrieval.RAG_NEIGHBOR_PAGES = k, n
                    seen = {"search": [], "neighbor": []}

                    def recording_search(query):          # 検索の上位と、前後として足したページを分けて記録する
                        results = original_search(query)
                        for r in results:
                            seen["neighbor" if r.get("source") == "neighbor" else "search"].append(r["page_id"])
                        return results
                    retrieval.search = recording_search
                    try:
                        record = {"qid": qid, "k": k, "neighbors": n, "rep": rep, **run_once(agent, QUESTIONS[qid])}
                    finally:
                        retrieval.search = original_search
                    record["search_ids"], record["neighbor_ids"] = seen["search"], seen["neighbor"]
                    append_run(OUT, record)
                    runs.append(record)
                    print(f"{qid} K={k} neighbors={n} rep{rep}: {coverage(record, qid)} +{neighbor_only_evidence(record, qid)} {record.get('elapsed')}s")
    report(runs)


if __name__ == "__main__":
    main()
