"""第5回: 用語集と各回の要点を MCP サーバーとして公開する。

使い方:
    uv run python -m app.agent --mcp --list-tools   # このサーバーが公開するツールを一覧する（APIキー不要）
    uv run python -m app.mcp_server --http          # Streamable HTTP で起動する（http://127.0.0.1:8000/mcp）

引数なしで実行すると stdio（標準入出力）で待ち受ける。これは MCP クライアント（app.agent の --mcp や
Copilot Chat）がサブプロセスとして起動する使い方なので、手で実行すると入力待ちのまま止まって見える。

第3回では tools.py の関数を agent.py に直接登録した。MCP サーバーにすると、同じ関数を
Pydantic AI 以外のクライアント（Copilot Chat など）からも、共通の手順で使えるようになる。
"""

import argparse
import functools

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from app import tools

# サーバーの名前と説明。クライアントに表示される（設定ファイル側のキー "glossary" とは別物）
server = MCPServer(
    "aie2026-glossary",
    instructions="AIE2026（AIエンジニアリング実践講座）の用語集と各回の要点を提供する。",
)

# 第3回と同じ関数を、そのまま MCP のツールとして公開する。docstring と型ヒントが説明文になる
server.tool()(tools.search_glossary)

server.tool()(tools.get_lecture_summary)  # 第5回 演習で追加


def tool_error_on_value_error(func):
    """ツール関数の ValueError（引数の誤り）を ToolError に変える（第5回 宿題）。

    MCP の SDK は、ToolError のメッセージはそのままモデルに返すが、それ以外の例外は
    「想定外のクラッシュ」として扱い、メッセージをサーバーの中に留める（モデルには
    "Error executing tool make_quiz" だけが届き、何を直せばよいか分からない）。
    """
    @functools.wraps(func)  # 名前・docstring・引数の型をそのまま引き継ぐ（ツールの説明文が変わらない）
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ValueError as e:
            raise ToolError(str(e)) from e
    return wrapper


server.tool()(tool_error_on_value_error(tools.make_quiz))  # 第3回で作ったツールも公開する（範囲外はエラー文を返す）
# save_learning_log は公開しない。承認（requires_approval）は Pydantic AI 側の仕組みで、MCP 越しには付かないため


def main() -> None:
    parser = argparse.ArgumentParser(description="用語集 MCP サーバー")
    parser.add_argument("--http", action="store_true", help="Streamable HTTP で起動する（既定は stdio）")
    args = parser.parse_args()
    if args.http:
        print("MCP サーバーを http://127.0.0.1:8000/mcp で起動します（Ctrl+C で停止）")
        server.run(transport="streamable-http")
    else:
        # stdio では標準出力がプロトコルの通信路になるので、print してはいけない
        server.run()


if __name__ == "__main__":
    main()
