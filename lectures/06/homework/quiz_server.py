"""第6回 宿題（実装）：make_quiz の範囲外の伝え方だけを変えた、比較用の MCP サーバー。

    uv run python lectures/06/homework/quiz_server.py return     # app/mcp_server.py と同じ（メッセージを return）
    uv run python lectures/06/homework/quiz_server.py value      # 同じメッセージで raise ValueError
    uv run python lectures/06/homework/quiz_server.py toolerror  # 同じメッセージで raise ToolError

3 つとも、ツールの名前・説明文・引数と、範囲外のメッセージの文面は同じ。違うのは、メッセージを
return で返すか、どの例外で投げるかだけ。stdio で待ち受けるので、quiz_error_compare.py から起動して使う。

2 つ目の引数に norange を付けると、説明文から範囲の一文（lecture は 1〜13…）を除く。説明文に範囲が
あると、モデルは第99回でツールを呼ばずに答えるので、渡し方の違いを比べるときに使う。
"""

import functools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # リポジトリ直下（app を import するため）

from mcp.server.mcpserver import MCPServer  # noqa: E402
from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402

from app import mcp_server, tools  # noqa: E402

MODES = ("return", "value", "toolerror")


RANGE_SENTENCE = "lecture は 1〜13（AIE2026 は全13回）。範囲外なら、指定できる回を書いたメッセージを返す。"


def build_server(mode: str, norange: bool = False) -> MCPServer:
    server = MCPServer("aie2026-glossary", instructions=f"比較用（make_quiz の範囲外: {mode}）")
    server.tool()(tools.search_glossary)
    server.tool()(tools.get_lecture_summary)
    error = {"value": ValueError, "toolerror": ToolError}.get(mode)

    @functools.wraps(mcp_server.make_quiz)  # 名前・説明文・引数を提出版とそろえる
    def make_quiz(lecture: int) -> str:
        if error is None:
            return mcp_server.make_quiz(lecture)  # 提出版そのもの（メッセージを return）
        try:
            return tools.make_quiz(lecture)
        except ValueError:
            raise error(mcp_server.out_of_range_message(lecture)) from None

    assert RANGE_SENTENCE in make_quiz.__doc__, "提出版の説明文が変わったら、ここも直す"
    if norange:
        make_quiz.__doc__ = make_quiz.__doc__.replace("\n    " + RANGE_SENTENCE, "")
    server.tool()(make_quiz)
    return server


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "return"
    if mode not in MODES:
        raise SystemExit(f"mode は {MODES} のどれか")
    build_server(mode, norange="norange" in sys.argv[2:]).run()
