"""第3回 宿題（基礎）: INSTRUCTIONS とツールの docstring を書き換え、ツールの呼ばれ方と回答を比べる。

使い方（リポジトリ直下で。要 GEMINI_API_KEY）:
    uv run python lectures/03/homework/basic_compare.py --out <出力ディレクトリ> [--reps 2]

app/agent.py と同じ部品（ツール関数・モデル）から、INSTRUCTIONS と説明文だけを差し替えたエージェントを
版（VARIANTS）ごとに組み立て、同じ質問を投げて、ツール呼び出し・requests・トークン数・回答を記録する。
ファイルを書き換えて `--trace` を何度も実行するのと同じことを、まとめて行う。
"""

import argparse
import inspect
import json
import sys
import time
from pathlib import Path

from pydantic_ai import Agent, Tool
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ToolCallPart, ToolReturnPart

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # リポジトリ直下（app パッケージ）を import できるようにする
from app import tools  # noqa: E402
from app.agent import INSTRUCTIONS, build_model  # noqa: E402

MINIMAL_INSTRUCTIONS = "あなたはAIエンジニアリング講座（AIE2026）の学習支援エージェントです。\n"

NARROW_GLOSSARY_DOC = """講座の用語集から用語を検索し、定義と、どの回で扱うかを返す。

この講座（AIE2026）に固有の言葉（講座の運営、提出の手順、講座 repo の決まりなど）を調べるときだけ使う。
LoRA や LLM のような一般的な AI の用語には使わず、自分の知識で答えること。query には調べたい用語を1つだけ入れる。
"""

QUIZ_DOC_WITHOUT_HIDING = """指定した回（1始まりの整数）の用語から1つを選び、「この用語の意味は？」という確認問題と答えを返す。

「第2回の確認問題を出して」「LoRAの回の復習クイズがほしい」のように、
学習者が理解度を確かめる問題を求めたときに使う。
"""


def doc(f) -> str:
    return inspect.cleandoc(f.__doc__)


# 版の名前: (INSTRUCTIONS, {ツール関数: 説明文})。説明文を変えない版は元の docstring を使う
VARIANTS = {
    "V0_base": (INSTRUCTIONS, {}),
    "V1_minimal_instructions": (MINIMAL_INSTRUCTIONS, {}),
    "V2_narrow_glossary_doc": (INSTRUCTIONS, {tools.search_glossary: NARROW_GLOSSARY_DOC}),
    "V3_quiz_doc_without_hiding": (INSTRUCTIONS, {tools.make_quiz: QUIZ_DOC_WITHOUT_HIDING}),
    # V3・V2 の結果を切り分けるために追加した版（INSTRUCTIONS を最小にして、説明文の効果だけを見る）
    "V4_minimal_and_quiz_doc_without_hiding": (MINIMAL_INSTRUCTIONS, {tools.make_quiz: QUIZ_DOC_WITHOUT_HIDING}),
    "V5_minimal_and_narrow_glossary_doc": (MINIMAL_INSTRUCTIONS, {tools.search_glossary: NARROW_GLOSSARY_DOC}),
}

QUESTIONS = {
    "Q1_lora_qlora": "LoRAとQLoRAの違いは？",
    "Q2_lecture3": "第3回では何を学ぶ？",
    "Q3_rag": "RAGとは何ですか？",
    "Q4_quiz": "第2回の内容から確認問題を1問出して",
    "Q5_general": "Pythonでリストを逆順にするには？",
}
# V3 は make_quiz の説明文だけを変えた版なので、クイズの質問だけで比べる
QUESTIONS_OF = {"V3_quiz_doc_without_hiding": ["Q4_quiz"],
                "V4_minimal_and_quiz_doc_without_hiding": ["Q4_quiz"],
                "V5_minimal_and_narrow_glossary_doc": ["Q1_lora_qlora", "Q3_rag", "Q5_general"]}


def build_agent(instructions: str, descriptions: dict) -> Agent:
    funcs = [tools.search_glossary, tools.get_lecture_summary, tools.make_quiz]
    return Agent(instructions=instructions,
                 tools=[Tool(f, description=inspect.cleandoc(descriptions.get(f, doc(f)))) for f in funcs])


def run_once(agent: Agent, question: str) -> dict:
    for attempt in range(3):
        try:
            result = agent.run_sync(question, model=build_model())
            break
        except ModelHTTPError as e:   # レート制限・混雑のときは待って再試行する
            if e.status_code not in (429, 503) or attempt == 2:
                raise
            time.sleep(30)
    calls = [{"tool": p.tool_name, "args": p.args_as_dict()}
             for m in result.all_messages() for p in m.parts if isinstance(p, ToolCallPart)]
    returns = [{"tool": p.tool_name, "content": str(p.content)[:200]}
               for m in result.all_messages() for p in m.parts if isinstance(p, ToolReturnPart)]
    u = result.usage
    return {"calls": calls, "returns": returns, "requests": u.requests, "input_tokens": u.input_tokens,
            "output_tokens": u.output_tokens, "output": result.output}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--reps", type=int, default=2)
    ap.add_argument("--variants", nargs="*", help="実行する版の名前（省略するとすべて）。結果は既存の JSON に追記する")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    path = out / "basic_compare.json"
    records = json.loads(path.read_text(encoding="utf-8")) if args.variants and path.exists() else []
    for vname, (instructions, descriptions) in VARIANTS.items():
        if args.variants and vname not in args.variants:
            continue
        agent = build_agent(instructions, descriptions)
        for qname in QUESTIONS_OF.get(vname, list(QUESTIONS)):
            for rep in range(args.reps):
                r = run_once(agent, QUESTIONS[qname])
                records.append({"variant": vname, "question": qname, "rep": rep, **r})
                calls = ", ".join(f"{c['tool']}({json.dumps(c['args'], ensure_ascii=False)})" for c in r["calls"]) or "（なし）"
                print(f"{vname:28s} {qname:14s} #{rep} req={r['requests']} in={r['input_tokens']:5d} | {calls}", flush=True)
                time.sleep(2)
    path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
