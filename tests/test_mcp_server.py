"""第6回: MCP サーバーとクライアントの配線テスト（LLM も API キーも使わない）。

app/mcp_servers.json の glossary サーバーを実際に起動し（stdio）、TestModel で
「ツールが MCP 経由で公開され、呼ばれ、結果が戻るか」を確かめる。
"""

import json

import pytest
from pydantic_ai.messages import ModelResponse, RetryPromptPart, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel

from app.mcp_agent import (
    MCP_CONFIG,
    ConfigError,
    build_mcp_agent,
    describe_servers,
    read_config,
)

GLOSSARY_TOOL = "glossary_search_glossary"  # 設定ファイルのサーバー名 "glossary" が前に付く


def _glossary_only_config(tmp_path):
    """設定のうち glossary サーバーだけを使う（演習で足した fetch などの外部サーバーは起動しない）。"""
    config = json.loads(MCP_CONFIG.read_text(encoding="utf-8"))
    assert "glossary" in config["mcpServers"], "app/mcp_servers.json に glossary サーバーが必要"
    path = tmp_path / "mcp_servers.json"
    path.write_text(
        json.dumps({"mcpServers": {"glossary": config["mcpServers"]["glossary"]}}), encoding="utf-8"
    )
    return path


def _parts(result, kind):
    return [p for m in result.all_messages() for p in m.parts if isinstance(p, kind)]


def test_glossary_server_exposes_search_tool(tmp_path):
    model = TestModel(call_tools=[])
    build_mcp_agent(_glossary_only_config(tmp_path)).run_sync("ツール一覧", model=model)

    offered = {t.name for t in model.last_model_request_parameters.function_tools}
    assert GLOSSARY_TOOL in offered  # 宿題でツールを足しても壊れないよう「含む」で判定


def test_glossary_result_comes_back_through_mcp(tmp_path):
    model = TestModel(call_tools=[GLOSSARY_TOOL])
    result = build_mcp_agent(_glossary_only_config(tmp_path)).run_sync("LoRAとは？", model=model)

    assert [p.tool_name for p in _parts(result, ToolCallPart)] == [GLOSSARY_TOOL]
    returns = _parts(result, ToolReturnPart)
    assert returns and returns[0].tool_name == GLOSSARY_TOOL
    assert str(returns[0].content).strip()  # 検索結果（または「見つかりませんでした」）が戻っている
    assert result.output


def test_describe_servers_tells_command_from_url(tmp_path):
    """コマンドで起動するサーバーと、URL で接続するサーバーを、表示で見分けられる。"""
    path = tmp_path / "mcp_servers.json"
    path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "glossary": {"command": "uv", "args": ["run", "python", "-m", "app.mcp_server"]},
                    "aws": {"url": "https://knowledge-mcp.global.api.aws"},
                }
            }
        ),
        encoding="utf-8",
    )
    assert describe_servers(path) == [
        "[server] glossary: コマンドで起動（uv run python -m app.mcp_server）",
        "[server] aws: URL に接続（https://knowledge-mcp.global.api.aws）",
    ]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('{"mcpServers": {"a": {"command": "uv"} "b": {"url": "https://example.com"}}}', "JSON の書き方の誤り"),
        ('{"servers": {}}', '"mcpServers" がありません'),
        ('{"mcpServers": {"a": {"args": []}}}', '"command" も "url" もありません'),
    ],
)
def test_config_mistakes_are_reported_in_words(tmp_path, text, expected):
    """設定ファイルの書き間違いは、どこをどう直すかが分かる言葉で知らせる。"""
    path = tmp_path / "mcp_servers.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ConfigError, match=expected):
        read_config(path)


# ---------------------------------------------------------------- 第6回 宿題（基礎・実装）
SUMMARY_TOOL = "glossary_get_lecture_summary"
QUIZ_TOOL = "glossary_make_quiz"


def _call_once(tool, args):
    """1 回目は tool を args で呼び、2 回目で回答するモデル（TestModel は引数を選べない）。"""
    def respond(messages, info):
        if not any(isinstance(m, ModelResponse) for m in messages):
            return ModelResponse(parts=[ToolCallPart(tool, args)])
        return ModelResponse(parts=[TextPart("回答")])
    return FunctionModel(respond)


def test_summary_and_quiz_tools_are_exposed_without_changing_the_agent(tmp_path):
    model = TestModel(call_tools=[])
    build_mcp_agent(_glossary_only_config(tmp_path)).run_sync("ツール一覧", model=model)

    offered = {t.name: t for t in model.last_model_request_parameters.function_tools}
    assert {GLOSSARY_TOOL, SUMMARY_TOOL, QUIZ_TOOL} <= offered.keys()
    assert "1〜13" in offered[QUIZ_TOOL].description  # 説明文の範囲が、MCP 越しにも見える


def test_quiz_through_mcp_returns_a_question(tmp_path):
    result = build_mcp_agent(_glossary_only_config(tmp_path)).run_sync(
        "第2回の確認問題", model=_call_once(QUIZ_TOOL, {"lecture": 2}))
    returns = [p for p in _parts(result, ToolReturnPart) if p.tool_name == QUIZ_TOOL]
    assert returns and json.loads(str(returns[0].content))["lecture"] == 2


@pytest.mark.parametrize("lecture", [0, 14, 99])
def test_out_of_range_lecture_comes_back_as_a_return_message(tmp_path, lecture):
    """範囲外は例外にせず、直し方を書いたメッセージを return する（[tool return] として届く）。"""
    result = build_mcp_agent(_glossary_only_config(tmp_path)).run_sync(
        f"第{lecture}回の確認問題", model=_call_once(QUIZ_TOOL, {"lecture": lecture}))
    returns = [p for p in _parts(result, ToolReturnPart) if p.tool_name == QUIZ_TOOL]
    assert returns, "範囲外でも、ツールの結果として戻る"
    assert f"第{lecture}回はありません" in str(returns[0].content) and "1〜13" in str(returns[0].content)
    assert not _parts(result, RetryPromptPart), "エラー（再試行の指示）にはならない"
