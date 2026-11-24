"""第6回: 用語集と各回の要点を MCP サーバーとして公開する。

使い方:
    uv run python -m app.mcp_agent --list-tools     # このサーバーが公開するツールを一覧する（APIキー不要）
    uv run python -m app.mcp_server --http          # Streamable HTTP で起動する（http://127.0.0.1:8000/mcp）

引数なしで実行すると stdio（標準入出力）で待ち受ける。これは MCP クライアント（app.mcp_agent など）が
サブプロセスとして起動する使い方なので、手で実行すると入力待ちのまま止まって見える。

第3回では tools.py の関数を agent.py に直接登録した。MCP サーバーにすると、同じ関数を
エージェントのプログラム（app/mcp_agent.py）からも、MCP に対応したほかのソフトウェアからも、
共通の手順で使えるようになる。
"""

import argparse

from mcp.server.mcpserver import MCPServer

from app import tools

# サーバーの名前と説明。クライアントに表示される（設定ファイル側のキー "glossary" とは別物）
server = MCPServer(
    "aie2026-glossary",
    instructions="AIE2026（AIエンジニアリング実践講座）の用語集と各回の要点を提供する。",
)

# 第3回と同じ関数を、そのまま MCP のツールとして公開する。docstring と型ヒントが説明文になる
server.tool()(tools.search_glossary)

# TODO(宿題・基礎): get_lecture_summary も公開しよう
server.tool()(tools.get_lecture_summary)


# 宿題・実装：第3回で作った make_quiz を公開する。tools.make_quiz は範囲外の回で ValueError を投げる
# （app/agent.py では ModelRetry としてモデルに直させる）。MCP サーバーでは例外にせず、
# 何を直せばよいかを書いたメッセージを return で返す（return と raise の違いは lectures/06/answer.md）
def out_of_range_message(lecture: int) -> str:
    """範囲外の回が指定されたときに返すメッセージ。有効な範囲と、用語がある回を示す。"""
    available = ", ".join(str(n) for n in sorted({e["lecture"] for e in tools.load_glossary()}))
    return (
        f"第{lecture}回はありません。AIE2026 は全{tools.NUM_LECTURES}回なので、lecture は "
        f"1〜{tools.NUM_LECTURES} の整数で指定してください。用語集に用語がある回: {available}"
    )


@server.tool()
def make_quiz(lecture: int) -> str:
    """指定した回（1始まりの整数）の用語から1つを選び、「この用語の意味は？」という確認問題と答えを返す。

    「第2回の確認問題を出して」「LoRAの回の復習クイズがほしい」のように、
    学習者が理解度を確かめる問題を求めたときに使う。問題だけを先に見せ、
    answer（用語集の定義）は学習者が答えたあとに示すこと。
    lecture は 1〜13（AIE2026 は全13回）。範囲外なら、指定できる回を書いたメッセージを返す。
    """
    try:
        return tools.make_quiz(lecture)
    except ValueError:
        return out_of_range_message(lecture)
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
