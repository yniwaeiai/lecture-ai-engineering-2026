"""第5回 宿題（基礎）: 設定ファイルを指定して、MCP 経由で見える search_glossary の説明文を表示する（API キー不要）。

使い方（リポジトリ直下で）:
    uv run python lectures/05/homework/show_desc.py lectures/05/homework/mcp_servers.stdio.json stdio
    uv run python lectures/05/homework/show_desc.py lectures/05/homework/mcp_servers.http.json  http
"""

import sys
from pathlib import Path

from pydantic_ai.models.test import TestModel

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # リポジトリ直下（app パッケージ）を import できるようにする
from app.agent import build_mcp_agent  # noqa: E402

model = TestModel(call_tools=[])
build_mcp_agent(Path(sys.argv[1])).run_sync("x", model=model)
for tool in model.last_model_request_parameters.function_tools:
    if tool.name.endswith("search_glossary"):
        print(sys.argv[2], "|", " / ".join(line.strip() for line in tool.description.strip().splitlines()[1:3]))
