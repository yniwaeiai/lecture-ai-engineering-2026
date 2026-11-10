"""発展の追記用：中身のない回答が、総合で合格になるかを確かめる。

τ-bench では空の応答を返すだけのエージェントが airline の 38% に合格していた
（Zhu et al., arXiv:2507.02825）。同じことが、この講座の採点で起きるかを見る。

演習の 10 件（data/eval/lec04_cases.jsonl）の回答を、次の 2 通りに置き換えて採点する。
  empty : 空文字
  mark  : 「関係する回：第N回」の 1 行だけ（N は元の回答の最後の行の回。無ければ 1）
採点基準は今の data/eval/rubric.md（STEP 3 で直した後）。モデルごとに reps 回。

使い方: uv run python lectures/04/homework/empty_answer_probe.py --models gemini-3.5-flash-lite gemini-3.5-flash --reps 3
"""

import argparse
import json
import re
import time
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from app.judge import build_judge, build_llm_model, judge_cases, overall

ROOT = Path(__file__).resolve().parents[3]
CASES = ROOT / "data/eval/lec04_cases.jsonl"
RUBRIC = ROOT / "data/eval/rubric.md"
OUT = Path(__file__).resolve().parent / "results/empty_answer_probe.json"


def variants(cases):
    empty, mark = [], []
    for c in cases:
        last = c["answer"].strip().splitlines()[-1] if c["answer"].strip() else ""
        m = re.search(r"第\s*(\d+)\s*回", last)
        n = m.group(1) if m else "1"
        empty.append({**c, "answer": ""})
        mark.append({**c, "answer": f"関係する回：第{n}回"})
    return {"empty": empty, "mark": mark}


def run_with_retry(agent, cases, tries=4):
    for i in range(tries):
        try:
            return judge_cases(agent, cases)
        except Exception as e:  # 429/500/503 など
            if i == tries - 1:
                raise
            print(f"  再試行 {i + 1}: {type(e).__name__}: {str(e)[:120]}")
            time.sleep(30)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--models", nargs="+", default=["gemini-3.5-flash-lite"])
    p.add_argument("--reps", type=int, default=3)
    a = p.parse_args()
    cases = [json.loads(l) for l in CASES.read_text(encoding="utf-8").splitlines() if l.strip()]
    rubric = RUBRIC.read_text(encoding="utf-8")
    results = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    for model in a.models:
        agent = build_judge(build_llm_model(model), rubric)
        for name, vc in variants(cases).items():
            for r in range(1, a.reps + 1):
                key = f"{model}/{name}/{r}"
                if key in results:
                    continue
                v = run_with_retry(agent, vc)
                per = {cid: {k: v[cid][k]["verdict"] for k in ["grounding", "scope", "hint", "clarity", "lecture_mark"]} for cid in v}
                for cid in per:
                    per[cid]["overall"] = overall(per[cid])
                results[key] = per
                OUT.parent.mkdir(parents=True, exist_ok=True)
                OUT.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
                n_pass = sum(x["overall"] == "pass" for x in per.values())
                print(f"{key}: 総合 pass {n_pass}/10")


if __name__ == "__main__":
    main()
