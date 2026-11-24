"""第6回 宿題（実装）：範囲外の回を、return で返すか raise するかで、モデルへの伝わり方を比べる。

    uv run python lectures/06/homework/quiz_error_compare.py --reps 3            # 実行して results/ に追記（要 GEMINI_API_KEY）
    uv run python lectures/06/homework/quiz_error_compare.py --reps 3 --norange  # 説明文から範囲の一文を除いた版
    uv run python lectures/06/homework/quiz_error_compare.py --report [--norange] # 集計だけ（API 不要）

モードごとに、quiz_server.py をそのモードで起動する設定ファイルを一時的に作り、app.mcp_agent と同じ
エージェント（build_mcp_agent）で同じ質問をする。外部のサーバー（fetch・aws）は起動しない。
モデルに渡った中身は、[tool return]（ToolReturnPart）と [tool error]（RetryPromptPart）を、そのまま記録する。
"""

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from pydantic_ai import capture_run_messages  # noqa: E402
from pydantic_ai.exceptions import UnexpectedModelBehavior  # noqa: E402
from pydantic_ai.messages import RetryPromptPart, ToolCallPart, ToolReturnPart  # noqa: E402

from app.mcp_agent import build_mcp_agent, build_model  # noqa: E402

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results" / "quiz_error_runs.jsonl"
MODES = ("return", "value", "toolerror")
QUESTION = "第99回のクイズを作って"


def config_for(mode: str, directory: Path, norange: bool) -> Path:
    path = directory / f"mcp_servers.{mode}.json"
    args = ["run", "python", str(HERE / "quiz_server.py"), mode] + (["norange"] if norange else [])
    spec = {"command": "uv", "args": args}
    path.write_text(json.dumps({"mcpServers": {"glossary": spec}}), encoding="utf-8")
    return path


def run_once(mode: str, directory: Path, question: str, norange: bool) -> dict:
    agent = build_mcp_agent(config_for(mode, directory, norange))
    record = {"mode": mode, "norange": norange, "question": question, "calls": [], "returns": [], "errors": []}
    started = time.perf_counter()
    with capture_run_messages() as messages:
        try:
            result = agent.run_sync(question, model=build_model())
            record["output"] = str(result.output)
            u = result.usage
            record["usage"] = {"input": u.input_tokens, "output": u.output_tokens, "requests": u.requests}
        except UnexpectedModelBehavior as e:  # 再試行の上限を超えたとき
            record["exception"] = f"{type(e).__name__}: {e}"
    record["elapsed"] = round(time.perf_counter() - started, 2)
    for message in messages:
        for part in message.parts:
            if isinstance(part, ToolCallPart):
                record["calls"].append({"tool": part.tool_name, "args": part.args_as_dict()})
            elif isinstance(part, ToolReturnPart):
                record["returns"].append({"tool": part.tool_name, "content": str(part.content)})
            elif isinstance(part, RetryPromptPart) and part.tool_name:
                # モデルに渡る文面そのもの（Pydantic AI が content に「直して」という一文を足したもの）
                record["errors"].append({"tool": part.tool_name, "to_model": part.model_response()})
    return record


def report(records: list[dict]) -> None:
    for mode in MODES:
        rows = [r for r in records if r["mode"] == mode]
        print(f"\n== {mode}（{len(rows)} 回）")
        for i, r in enumerate(rows, 1):
            calls = ", ".join(f"{c['tool']}({c['args']})" for c in r["calls"])
            usage = r.get("usage") or {}
            print(f"  [{i}] 呼び出し: {calls or 'なし'} / モデル応答 {usage.get('requests', '-')} 回"
                  f" / 入力 {usage.get('input', '-')} tokens / {r['elapsed']} 秒")
            for ret in r["returns"]:
                print(f"      [tool return] {ret['content'][:150]}")
            for err in r["errors"]:
                print(f"      [tool error]  {err['to_model'][:200]!r}")
            if "exception" in r:
                print(f"      例外: {r['exception'][:150]}")
            print(f"      回答: {r.get('output', '（なし）')[:160]!r}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reps", type=int, default=0)
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--question", default=QUESTION)
    parser.add_argument("--norange", action="store_true", help="説明文から範囲の一文を除いた版で比べる")
    args = parser.parse_args()
    if args.reps:
        RESULTS.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp:
            for rep in range(args.reps):
                for mode in MODES:  # モードを交互に流す（時間帯の偏りを避ける）
                    record = run_once(mode, Path(tmp), args.question, args.norange)
                    with RESULTS.open("a", encoding="utf-8") as f:
                        f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    print(f"rep{rep + 1} {mode}: {len(record['calls'])} calls", flush=True)
    records = [json.loads(line) for line in RESULTS.read_text(encoding="utf-8").splitlines() if line.strip()]
    report([r for r in records if r["question"] == args.question and r.get("norange", False) == args.norange])


if __name__ == "__main__":
    main()
