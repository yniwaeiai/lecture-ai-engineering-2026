"""第5回 宿題（基礎）: 設定ファイルを指定して MCP 経由で質問し、ツール呼び出しと requests を 1 行で表示する（要 GEMINI_API_KEY）。

使い方（リポジトリ直下で）:
    uv run python lectures/05/homework/ask_via.py lectures/05/homework/mcp_servers.http.json "RAGとは何ですか？" http
"""

import sys
from pathlib import Path

from pydantic_ai.messages import ToolCallPart

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # リポジトリ直下（app パッケージ）を import できるようにする
from app.agent import build_mcp_agent, build_model  # noqa: E402

result = build_mcp_agent(Path(sys.argv[1])).run_sync(sys.argv[2], model=build_model())
calls = [f"{p.tool_name}({p.args})" for m in result.all_messages() for p in m.parts if isinstance(p, ToolCallPart)]
print(sys.argv[3], "| calls:", calls or "なし", "| requests:", result.usage.requests, "|", result.output[:60].replace("\n", " "))
