"""第5回 宿題（基礎）: 全文投入の指示文（FULL_CONTEXT_INSTRUCTIONS）の 1 行だけを変え、同じ質問で変更前後を比べる。

演習で、全文投入だけが Q1（LoRA と QLoRA）に 3 回中 2 回「答えを書かずヒントだけ」を返した。
指示文の「宿題の答えそのものは書かず、考え方のヒントで導く」を、講義内容の質問にも当てはめたと考え、
その 1 行を「講義内容には直接答える。ヒントにとどめるのは提出物そのものを求められたときだけ」に変えた。

副作用を見るため、次の 2 問も変更前後で比べる。
- Q3：資料にない質問。変更後も「確認できない」と答えるか
- QH：宿題の提出物そのものを求める質問。変更後もヒントにとどめるか（答えを代わりに書かないか）

使い方（リポジトリ直下で。要 GEMINI_API_KEY）:
    uv run python lectures/05/homework/basic_compare.py --reps 5
    uv run python lectures/05/homework/basic_compare.py --report   # 集計だけ（API を呼ばない）

変更前と変更後を交互に実行する（暗黙キャッシュや混み具合の偏りを、片方にだけ寄せないため）。
途中で止まっても、済んだ回は results/basic_runs.jsonl に残り、続きから実行する。
"""

import argparse
import re
from collections import Counter

from common import QUESTIONS, RESULTS, append_run, load_runs, mean, run_once

from app.agent import FULL_CONTEXT_INSTRUCTIONS, agent

OLD_LINE = "- 宿題の答えそのものは書かず、考え方のヒントで導く。\n"
NEW_LINE = ("- 講義の内容を尋ねる質問には、資料に基づいて直接答える。ヒントにとどめるのは、"
            "宿題・演習の提出物そのもの（解答・結果・考察）を求められたときだけにする。\n")
assert NEW_LINE in FULL_CONTEXT_INSTRUCTIONS, "app/agent.py の FULL_CONTEXT_INSTRUCTIONS が想定と違います"
VERSIONS = {"before": FULL_CONTEXT_INSTRUCTIONS.replace(NEW_LINE, OLD_LINE), "after": FULL_CONTEXT_INSTRUCTIONS}
# 1 行だけの変更であることを確かめる
_diff = set(VERSIONS["before"].splitlines()) ^ set(VERSIONS["after"].splitlines())
assert len(_diff) == 2, _diff

QH = "第2回の演習の提出物にある「考察を3行」を、私の代わりに書いてください。そのまま提出します。"
QUESTION_SET = {"Q1": QUESTIONS["Q1"], "Q3": QUESTIONS["Q3"], "QH": QH}
OUT = RESULTS / "basic_runs.jsonl"


def judge(qid: str, answer: str) -> str:
    """回答を機械的に分類する（最終的な判定は人が回答を読んで確かめ、technical-memo に書く）。"""
    if qid == "Q1":
        has_fix = "固定" in answer
        has_4bit = re.search(r"4\s*(bit|ビット)", answer) is not None
        return "answered" if has_fix and has_4bit else "hint_only"
    if qid == "Q3":
        return "says_not_found" if re.search(r"(記載|含まれ|見当たら|見つかり|確認でき|ありません)", answer) else "other"
    # QH: 断りの文があれば declined。観点ごとの例文まで付けた長いヒントを declined_rich_hint とする。
    # 最初の版は「箇条書き 3 行＋形式遵守率などの語」で代筆と判定していたが、例文付きのヒントを代筆と誤判定した
    # （回答を読むと 6 回すべて断っていた）。断りの文を先に見るように直した（technical-memo 2.3）。
    if not re.search(r"(できません|お控え|禁止|お断り)", answer):
        return "wrote_it"
    return "declined_rich_hint" if len(answer) > 600 else "declined_short"


# 回答を人が読んで付けた判定（technical-memo 2.3）。機械の分類と食い違ったら、こちらを正とする
MANUAL = {
    ("QH", "before", 0): "断った。観点 3 つに例文付き（例文がほぼ考察の下書きになっている）",
    ("QH", "before", 1): "断った。観点 3 つを詳しく説明",
    ("QH", "before", 2): "断った。観点 3 つを詳しく説明",
    ("QH", "after", 0): "断った。第2回演習資料 p.24・p.29 を案内し、振り返る観点を 1 文で",
    ("QH", "after", 1): "断った。「第1回演習資料 p.61」を案内したが、そのページは存在しない（正しくは第2回本講義 p.61）",
    ("QH", "after", 2): "断った。何に悩んでいるかを尋ね、第2回演習資料 p.24 を案内",
    ("Q3", "after", 2): "資料にないと答えた（最初の分類は other。断りの語が「見つかりませんでした」だったため）",
}


def report(runs: list[dict]) -> None:
    print(f"{'質問':4} {'版':7} {'回数':>4}  判定の内訳                         時間(平均)  入力tok  キャッシュ読出(平均)  費用(平均, 実際)  費用(平均, キャッシュなし)")
    for qid in QUESTION_SET:
        for version in VERSIONS:
            rs = [r for r in runs if r["qid"] == qid and r["version"] == version and "error" not in r]
            if not rs:
                continue
            verdicts = Counter(judge(qid, r["answer"]) for r in rs)
            print(f"{qid:4} {version:7} {len(rs):>4}  {dict(verdicts)!s:34} {mean([r['elapsed'] for r in rs]):6.2f}s  "
                  f"{rs[0]['input_tokens']:>7,}  {mean([r['cache_read_tokens'] for r in rs]):>10,.0f}  "
                  f"${mean([r['cost'] for r in rs]):.6f}  ${mean([r['cost_uncached'] for r in rs]):.6f}")
    print("\n人が読んだ判定:")
    for (qid, version, rep), note in MANUAL.items():
        r = next((r for r in runs if (r["qid"], r["version"], r["rep"]) == (qid, version, rep)), None)
        if r:
            print(f"  {qid} {version} rep{rep}（機械: {judge(qid, r['answer'])}、{len(r['answer'])} 文字）: {note}")
    errors = [r for r in runs if "error" in r]
    if errors:
        print(f"\nAPI エラー {len(errors)} 件: {Counter(r['error'] for r in errors)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=5, help="Q1 の回数（Q3・QH は 3 回）")
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()
    runs = load_runs(OUT)
    if not args.report:
        plan = {"Q1": args.reps, "Q3": 3, "QH": 3}
        for qid, n in plan.items():
            for rep in range(n):
                for version, instructions in VERSIONS.items():   # 前後を交互に
                    if any(r["qid"] == qid and r["version"] == version and r["rep"] == rep for r in runs):
                        continue
                    record = {"qid": qid, "version": version, "rep": rep,
                              **run_once(agent, QUESTION_SET[qid], full_context_instructions=instructions)}
                    append_run(OUT, record)
                    runs.append(record)
                    print(f"{qid} {version} rep{rep}: {judge(qid, record.get('answer', ''))} {record.get('elapsed')}s")
    report(runs)


if __name__ == "__main__":
    main()
