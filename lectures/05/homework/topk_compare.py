"""第5回 宿題（基礎 b）: app/config.py の RAG_TOP_K（ベクトル検索で返す件数）だけを 3・5・10 に変え、同じ質問で比べる。

既定のエージェント（search_materials だけを持つ）を使う。RAG_TOP_K は app.retrieval が import 時に読み込むので、
実行中に app.retrieval.RAG_TOP_K を差し替える（app/config.py を書き換えるのと同じ効果。--trace の実行例は
config.py を書き換えて取った。technical-memo 2.5）。

使い方（リポジトリ直下で。要 GEMINI_API_KEY）:
    uv run python lectures/05/homework/topk_compare.py --reps 3
    uv run python lectures/05/homework/topk_compare.py --report
"""

import argparse

from common import QUESTIONS, RESULTS, append_run, coverage, load_runs, mean, run_once

import app.retrieval as retrieval
from app.agent import agent

KS = [3, 5, 10]
QIDS = ["Q1", "Q2", "Q3", "Q4"]
OUT = RESULTS / "topk_runs.jsonl"


def report(runs):
    print(f"{'質問':4} {'K':>3} {'回':>2}  根拠の取得/引用(平均)  検索回数  返ったページ(異なり)  時間     入力tok   出力tok  応答  費用(キャッシュなし)")
    for qid in QIDS:
        for k in KS:
            rs = [r for r in runs if r["qid"] == qid and r["k"] == k and "error" not in r]
            if not rs:
                continue
            cov = [coverage(r, qid) for r in rs]
            of = cov[0]["of"]
            print(f"{qid:4} {k:>3} {len(rs):>2}  {mean([c['retrieved'] for c in cov]):.1f}/{of} , {mean([c['cited'] for c in cov]):.1f}/{of}"
                  f"          {mean([len(r['tool_calls']) for r in rs]):.1f}      {mean([c['unique_pages_returned'] for c in cov]):5.1f}"
                  f"           {mean([r['elapsed'] for r in rs]):5.2f}s  {mean([r['input_tokens'] for r in rs]):7,.0f}  {mean([r['output_tokens'] for r in rs]):6,.0f}"
                  f"   {mean([r['requests'] for r in rs]):.1f}  ${mean([r['cost_uncached'] for r in rs]):.6f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()
    runs = load_runs(OUT)
    if not args.report:
        for rep in range(args.reps):
            for qid in QIDS:
                for k in KS:
                    if any(r["qid"] == qid and r["k"] == k and r["rep"] == rep for r in runs):
                        continue
                    retrieval.RAG_TOP_K = k
                    record = {"qid": qid, "k": k, "rep": rep, **run_once(agent, QUESTIONS[qid])}
                    append_run(OUT, record)
                    runs.append(record)
                    print(f"{qid} K={k} rep{rep}: {coverage(record, qid)} {record.get('elapsed')}s")
    report(runs)


if __name__ == "__main__":
    main()
