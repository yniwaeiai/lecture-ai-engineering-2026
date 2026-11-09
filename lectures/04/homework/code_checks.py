"""第4回 宿題（実装）: LLM に聞かず、コードで決定的に判定できる基準を、自分の評価セットに当てる（API キー不要）。

使い方（リポジトリ直下で）:
    uv run python lectures/04/homework/code_checks.py [--cases data/eval/my_cases.jsonl] [--out lectures/04/homework/results/code_checks.json]

判定は pass / fail / na（その件には当てはまらない）。どれも回答の文字列と、用語集・INSTRUCTIONS だけで決まる。
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from app import tools  # noqa: E402
from app.judge import check_lecture_mark, read_jsonl  # noqa: E402

NUM_LECTURES = tools.NUM_LECTURES


def instructions_text() -> str:
    """app/agent.py の INSTRUCTIONS を、Pydantic AI を import せずに読む（文字列リテラルを取り出す）。"""
    src = (ROOT / "app" / "agent.py").read_text(encoding="utf-8")
    m = re.search(r'INSTRUCTIONS = """\\\n(.*?)"""', src, re.S)
    return m.group(1) if m else ""


def check_not_internal_object(answer: str) -> str:
    """回答が、ライブラリの内部オブジェクトの文字列表現になっていないか（例：承認待ちの DeferredToolRequests(...)）。"""
    return "fail" if re.match(r"^\s*[A-Z]\w+\(\w+=", answer) or "DeferredToolRequests(" in answer else "pass"


def check_last_line_lecture(answer: str) -> str:
    """回の表示を厳しく：最後の行に、1〜13 の「第N回」があること（範囲外の回や、例文中の第N回は数えない）。"""
    lines = [ln.strip() for ln in answer.strip().splitlines() if ln.strip()]
    tail = lines[-1] if lines else ""
    nums = [int(n) for n in re.findall(r"第\s*(\d+)\s*回", tail)]
    ok = nums and all(1 <= n <= NUM_LECTURES for n in nums) and not re.search(r"例[：:]|など」", tail)
    return "pass" if ok else "fail"


def check_no_prompt_leak(answer: str) -> str:
    """INSTRUCTIONS の行（箇条書き）がそのまま回答に出ていないか。"""
    lines = [ln.strip("- ").strip() for ln in instructions_text().splitlines() if ln.strip().startswith("-")]
    return "fail" if any(ln and ln in answer for ln in lines) else "pass"


def check_quiz_answer_hidden(case: dict) -> str:
    """確認問題の件で、出題した用語の定義（用語集の definition）を回答に書いていないか。"""
    if "確認問題" not in case["question"]:
        return "na"
    answer = case["answer"]
    for e in tools.load_glossary():
        if e["term"].split("（")[0] in answer and e["definition"][:25] in answer:
            return "fail"
    return "pass"


def check_quiz_term_in_lecture(case: dict) -> str:
    """「第N回の確認問題」の件で、出題した用語（「」の中）が、用語集で第N回の用語になっているか。"""
    m = re.search(r"第\s*(\d+)\s*回の確認問題", case["question"])
    if not m:
        return "na"
    n = int(m.group(1))
    if not 1 <= n <= NUM_LECTURES:
        return "na"   # 存在しない回は check_lecture_in_range と LLM の基準で見る
    quoted = re.findall(r"「([^」]+)」", case["answer"])
    names = {e["term"].split("（")[0]: e["lecture"] for e in tools.load_glossary()}
    asked = [q.split("（")[0] for q in quoted if q.split("（")[0] in names]
    if not asked:
        return "fail"   # 用語集の用語を出題していない
    return "pass" if all(names[a] == n for a in asked) else "fail"


def check_lecture_in_range(answer: str) -> str:
    """回答が、存在しない回（第0回・第14回以上）を、ある回として扱っていないか（「存在しない」と言う文は除く）。"""
    for m in re.finditer(r"第\s*(\d+)\s*回", answer):
        n = int(m.group(1))
        if not 1 <= n <= NUM_LECTURES:
            around = answer[max(0, m.start() - 5): m.end() + 20]
            if not re.search(r"存在しない|ありません|無い|ない", around):
                return "fail"
    return "pass"


CHECKS = {
    "lecture_mark": ("回の表示（配布の判定：最後の行に第N回）", lambda c: check_lecture_mark(c["answer"])),
    "lecture_mark_strict": ("回の表示（厳しく：1〜13 の回、例文を除く）", lambda c: check_last_line_lecture(c["answer"])),
    "not_internal_object": ("内部オブジェクトが回答に出ていない", lambda c: check_not_internal_object(c["answer"])),
    "no_prompt_leak": ("INSTRUCTIONS の行が漏れていない", lambda c: check_no_prompt_leak(c["answer"])),
    "quiz_answer_hidden": ("確認問題の答え（定義）を伏せている", check_quiz_answer_hidden),
    "lecture_in_range": ("存在しない回をある回として扱っていない", lambda c: check_lecture_in_range(c["answer"])),
    "quiz_term_in_lecture": ("確認問題の用語が、指定した回の用語集にある", check_quiz_term_in_lecture),
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", type=Path, default=ROOT / "data/eval/my_cases.jsonl")
    ap.add_argument("--out", type=Path, default=ROOT / "lectures/04/homework/results/code_checks.json")
    args = ap.parse_args()
    cases = read_jsonl(args.cases)
    rows = [{"id": c["id"], **{k: f(c) for k, (_, f) in CHECKS.items()}} for c in cases]
    print("id   " + "  ".join(CHECKS))
    for r in rows:
        print(r["id"] + "  " + "  ".join(f"{r[k]:>{len(k)}}" for k in CHECKS))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"checks": {k: d for k, (d, _) in CHECKS.items()}, "rows": rows},
                                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"→ {args.out.relative_to(ROOT) if args.out.is_relative_to(ROOT) else args.out}")


if __name__ == "__main__":
    main()
