"""第3回 宿題（発展 a）: ADK 版エージェントに演習と同じ質問を投げ、イベントの流れを記録する。

使い方（リポジトリ直下で。google-adk を入れた環境。要 GEMINI_API_KEY）:
    python lectures/03/homework/adk/adk_compare.py --out <出力ディレクトリ>

ADK では、エージェントの実行は Runner が行い、途中経過はすべて Event として流れてくる。
Pydantic AI の result.all_messages() にあたる情報を、イベントから読み出して記録する。
"""

import argparse
import asyncio
import json
import re
import sys
import tempfile
from pathlib import Path

from google.adk.runners import InMemoryRunner
from google.genai import types

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))
from aie_agent.agent import INSTRUCTIONS, root_agent  # noqa: E402
from app import tools  # noqa: E402

CONFIRM = "adk_request_confirmation"  # require_confirmation=True のツールを呼ぶと、ADK が代わりに出す関数呼び出しの名前

# (名前, 質問, 確認を求められたときの答え)
CASES = [
    ("lecnn_start", "AIE2026の講座で使う「lecNN-start タグ」とは何ですか？", None),
    ("lora_qlora", "LoRAとQLoRAの違いは？", None),
    ("quiz", "第2回の内容から確認問題を1問出して", None),
    ("save_approve", "第2回でLoRAのランクrは表現力とメモリのトレードオフだと学んだ。学習ログに保存して", True),
    ("save_deny", "第3回でツールの説明文が大事だとわかった。記録しておいて", False),
]


def check_instructions_in_sync() -> None:
    src = (ROOT / "app" / "agent.py").read_text(encoding="utf-8")
    original = re.search(r'INSTRUCTIONS = """\\\n(.*?)"""', src, re.S).group(1)
    assert original == INSTRUCTIONS, "ADK 版の INSTRUCTIONS が app/agent.py と食い違っています"


async def run_case(runner: InMemoryRunner, question: str, confirm_answer) -> dict:
    session = await runner.session_service.create_session(app_name=runner.app_name, user_id="u")
    log = {"events": [], "llm_responses": 0, "input_tokens": 0, "output_tokens": 0, "final": ""}
    message = types.Content(role="user", parts=[types.Part(text=question)])
    while message is not None:
        pending = None
        async for event in runner.run_async(user_id="u", session_id=session.id, new_message=message):
            if event.usage_metadata:   # モデルの応答 1 回ごとに使用量が付く
                log["llm_responses"] += 1
                log["input_tokens"] += event.usage_metadata.prompt_token_count or 0
                log["output_tokens"] += event.usage_metadata.candidates_token_count or 0
            for part in (event.content.parts if event.content else []):
                if part.function_call:
                    call = part.function_call
                    log["events"].append({"author": event.author, "type": "function_call", "name": call.name, "args": call.args})
                    if call.name == CONFIRM:
                        pending = call
                elif part.function_response:
                    resp = part.function_response
                    log["events"].append({"author": event.author, "type": "function_response", "name": resp.name,
                                          "response": str(resp.response)[:160]})
                elif part.text and event.author == root_agent.name and not part.thought:
                    log["final"] += part.text
        message = None
        if pending is not None and confirm_answer is not None:
            # 確認の要求に、利用者の答えを「関数の応答」として返すと、ADK が元のツールを実行（または中止）して続きを進める
            message = types.Content(role="user", parts=[types.Part(function_response=types.FunctionResponse(
                id=pending.id, name=CONFIRM, response={"confirmed": confirm_answer}))])
            log["events"].append({"author": "user", "type": "confirmation", "confirmed": confirm_answer})
            confirm_answer = None
    return log


async def main_async(out: Path) -> None:
    check_instructions_in_sync()
    tools.LEARNING_LOG_DIR = Path(tempfile.mkdtemp())   # 学習ログは一時ディレクトリに書く
    runner = InMemoryRunner(agent=root_agent, app_name="aie_agent")
    records = {}
    for name, question, confirm in CASES:
        records[name] = {"question": question, **await run_case(runner, question, confirm)}
        records[name]["saved_files"] = sorted(p.name for p in tools.LEARNING_LOG_DIR.glob("*.md"))
        r = records[name]
        calls = ", ".join(f"{e['name']}({json.dumps(e['args'], ensure_ascii=False)[:80]})"
                          for e in r["events"] if e["type"] == "function_call")
        print(f"{name:13s} llm={r['llm_responses']} in={r['input_tokens']:5d} | {calls}", flush=True)
    (out / "adk_compare.json").write_text(json.dumps(records, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    out = Path(ap.parse_args().out)
    out.mkdir(parents=True, exist_ok=True)
    asyncio.run(main_async(out))


if __name__ == "__main__":
    main()
