"""第4回 宿題（基礎）: 採点のモデルだけを変え、同じ設定で複数回採点して、一致率と判定の揺れを比べる。

使い方（リポジトリ直下で。要 GEMINI_API_KEY）:
    uv run python lectures/04/homework/model_compare.py --models gemini-3.5-flash-lite gemini-3.5-flash --reps 3

採点は app.judge と同じ関数（build_judge・judge_cases・summarize）で行う。ラベルは集計にしか使わないので、
1 回の採点結果を「GPT-6 のラベル（lectures/04/labels.jsonl）」と「講師のラベル」の両方と比べる。
"""

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from pydantic_ai.exceptions import ModelHTTPError  # noqa: E402

from app.judge import (DEFAULT_CASES, DEFAULT_RUBRIC, build_judge, build_llm_model,  # noqa: E402
                       judge_cases, load_labels, read_jsonl, summarize)

LABELS = {"gpt6": ROOT / "lectures/04/labels.jsonl",
          "instructor": ROOT / "lectures/04/reference/labels_instructor.jsonl"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", required=True)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--out", type=Path, default=ROOT / "lectures/04/homework/results/model_compare.json")
    args = ap.parse_args()
    cases = read_jsonl(DEFAULT_CASES)
    rubric = DEFAULT_RUBRIC.read_text(encoding="utf-8")
    labels = {k: load_labels(p) for k, p in LABELS.items()}
    # 途中で止まっても、済んだ回は残して続きから実行する
    runs = json.loads(args.out.read_text(encoding="utf-8")) if args.out.exists() else []
    done = {(r["model"], r["rep"]) for r in runs}
    for model_name in args.models:
        agent = build_judge(build_llm_model(model_name), rubric)
        for rep in range(args.reps):
            if (model_name, rep) in done:
                continue
            for attempt in range(4):   # サーバー側の一時的なエラー（500・503・429）は待って 1 回分をやり直す
                try:
                    verdicts = judge_cases(agent, cases, wait=1.0)
                    break
                except ModelHTTPError as e:
                    if e.status_code not in (429, 500, 503) or attempt == 3:
                        raise
                    print(f"\n[{e.status_code}] 30 秒待って再試行します")
                    time.sleep(30)
            runs.append({"model": model_name, "rep": rep, "verdicts": verdicts,
                         "summary": {k: summarize(cases, verdicts, lab) for k, lab in labels.items()}})
            args.out.write_text(json.dumps(runs, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"→ {args.out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
